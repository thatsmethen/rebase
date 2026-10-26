#include "StreamEngine.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <new>
#include <string>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
using namespace rebase;
namespace {
uint64_t checks = 0;
uint64_t long_hash = 0;
uint32_t long_source_peak = 0, long_endpoint_peak = 0;
uint32_t oracle_completed = 0;
bool progress_diagnostics = false;
std::atomic<uint64_t> status_samples{0};
void check(bool value, const char *message) { ++checks; if (!value) { std::fprintf(stderr, "stream control failed: %s\n", message); std::exit(1); } }
RBAudioStreamDescriptor descriptor(uint64_t frames, uint32_t rate, uint32_t capacity = 4096) {
    return {1,rate,2,std::min<uint32_t>(4096,capacity),1,frames,capacity,capacity,0,0};
}
void tick() { std::this_thread::sleep_for(std::chrono::microseconds(100)); }
template<class Predicate> void until(Predicate predicate) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (!predicate()) { check(std::chrono::steady_clock::now() < deadline, "bounded wait"); tick(); }
}
std::vector<float> source(uint32_t frames) {
    std::vector<float> samples(size_t(frames) * 2);
    for (uint32_t i=0;i<frames;++i) { samples[size_t(i)*2] = float(int(i % 127)-63)/128; samples[size_t(i)*2+1] = float(int(i % 83)-41)/128; }
    return samples;
}
bool valid_status(const RBAudioStreamStatus &s) {
    return s.source_position <= s.source_consumed && s.source_consumed <= s.source_accepted && s.source_accepted <= s.source_frames &&
        s.endpoint_position <= s.endpoint_submitted && s.endpoint_submitted <= s.endpoint_produced &&
        s.source_queued <= s.source_capacity && s.endpoint_queued <= s.endpoint_capacity &&
        s.source_peak <= s.source_capacity && s.endpoint_peak <= s.endpoint_capacity &&
        (!s.primed || s.phase != RB_AUDIO_PRIMING) &&
        (!s.source_eof || s.source_accepted == s.source_frames) &&
        (s.endpoint_total_final ? (s.source_eof && s.source_consumed == s.source_frames && s.endpoint_total == s.endpoint_produced) : s.endpoint_total == 0) &&
        (s.phase != RB_AUDIO_FINISHED || (s.endpoint_total_final && s.endpoint_position == s.endpoint_total && s.source_position == s.source_frames));
}
void progress_report(const char *control, uint32_t from, uint32_t to, uint64_t frames,
                     uint32_t partition, uint64_t accepted, uint64_t played,
                     const RBAudioStreamStatus &s, std::chrono::steady_clock::time_point started) {
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - started).count();
    std::fprintf(stderr, "stream diagnostic: control=%s source_rate=%u endpoint_rate=%u frames=%llu partition=%u elapsed_ms=%lld accepted=%llu consumed=%llu produced=%llu played=%llu source_queued=%u endpoint_queued=%u phase=%u eof=%u final=%u result=%d completed_oracles=%u long_completed=%u long_fnv1a64=%llu\n",
        control, from, to, static_cast<unsigned long long>(frames), partition, static_cast<long long>(elapsed),
        static_cast<unsigned long long>(accepted), static_cast<unsigned long long>(s.source_consumed),
        static_cast<unsigned long long>(s.endpoint_produced), static_cast<unsigned long long>(played),
        s.source_queued, s.endpoint_queued, s.phase, s.source_eof, s.endpoint_total_final, s.result,
        oracle_completed, long_hash != 0 ? 1u : 0u, static_cast<unsigned long long>(long_hash));
}
void exact(uint32_t from, uint32_t to, uint32_t frames, uint32_t partition, uint32_t capacity) {
    auto input = source(frames); std::vector<float> oracle;
    check(convert_snapshot(input.data(),frames,from,to,oracle)==0,"snapshot oracle");
    StreamEngine engine(descriptor(frames,from,capacity),to,128); check(engine.start()==0,"start");
    std::vector<float> result; result.reserve(oracle.size());
    uint64_t accepted=0,sequence=0; bool finished=false,playing=false;
    const auto started=std::chrono::steady_clock::now(), deadline=started+std::chrono::seconds(10);
    std::array<float,1024> block{};
    while(true) {
        bool progressed=false;
        auto s=engine.status(); check(s.result==0,"producer no error"); check(valid_status(s),"public status invariants");
        check(s.source_peak<=capacity && s.endpoint_peak<=capacity,"bounded queues");
        check(s.endpoint_total_final || s.endpoint_total==0,"unknown total not estimated");
        if(accepted<frames) {
            const uint32_t count=static_cast<uint32_t>(std::min<uint64_t>(partition,frames-accepted));
            const int code=engine.submit(1,sequence,accepted,input.data()+accepted*2,count);
            check(code==0 || code==RB_AUDIO_BACKPRESSURE,"submit/backpressure");
            if(!code) { accepted+=count; ++sequence; progressed=true; }
        } else if(!finished) { check(engine.finish(1,sequence,accepted)==0,"finish"); finished=true; progressed=true; }
        s=engine.status();
        if(s.primed && !playing) {
            const auto code=engine.play();
            if(code)progress_report("primed play rejected",from,to,frames,partition,accepted,result.size()/2,engine.status(),started);
            check(code==0,"play"); playing=true; progressed=true;
        }
        // Deterministic fake endpoint waits for enough queued data rather than
        // claiming a real-time scheduling guarantee. Separate controls underrun.
        if(playing && (s.endpoint_queued>=512 || s.endpoint_total_final)) {
            uint32_t actual=0; check(engine.available(512,actual)==0,"available");
            if(actual) {
                check(engine.consume(block.data(),actual)==0,"consume"); engine.submitted(actual);
                result.insert(result.end(),block.data(),block.data()+size_t(actual)*2);
                engine.observe(result.size()/2);
                progressed=true;
            }
        }
        if(playing) engine.observe(result.size()/2);
        s=engine.status();
        if(s.phase==RB_AUDIO_FINISHED) { check(s.source_position==frames,"finished source end"); break; }
        check(s.source_position<frames,"no early source end");
        if(std::chrono::steady_clock::now()>=deadline) {
            progress_report("conversion deadline",from,to,frames,partition,accepted,result.size()/2,s,started);
            check(false,"conversion deadline");
        }
        // This authored endpoint is not clock-paced. One-frame admission must
        // not incur 16,403 deliberate sleeps merely to compare converter bytes.
        // Yield during progress, and retain bounded polling only while idle.
        if(progressed)std::this_thread::yield();else tick();
    }
    check(result.size()==oracle.size(),"oracle output count");
    check(std::memcmp(result.data(),oracle.data(),result.size()*4)==0,"bit exact oracle output");
    ++oracle_completed;
    if(progress_diagnostics)progress_report("conversion completed",from,to,frames,partition,accepted,result.size()/2,engine.status(),started);
    engine.cancel(); check(engine.status().phase==RB_AUDIO_CANCELLED,"cancel barrier");
    check(engine.submit(1,sequence,accepted,input.data(),1)==RB_AUDIO_STATE,"cancel late block");
}
void protocol() {
    auto input=source(4096); StreamEngine e(descriptor(100000,48000),48000,128); check(e.start()==0,"protocol start");
    check(e.play()==RB_AUDIO_STATE,"unprimed play rejected");
    check(e.submit(2,0,0,input.data(),4096)==RB_AUDIO_STALE,"foreign generation");
    check(e.submit(1,1,0,input.data(),4096)==RB_AUDIO_PROTOCOL,"skipped sequence");
    check(e.submit(1,0,1,input.data(),4096)==RB_AUDIO_PROTOCOL,"wrong start");
    check(e.finish(1,0,0)==RB_AUDIO_PROTOCOL,"premature eof");
    input[0]=INFINITY; check(e.submit(1,0,0,input.data(),4096)==RB_AUDIO_ARGUMENT,"nonfinite input"); input[0]=0;
    uint64_t accepted=0,seq=0; int code=0;
    until([&]{ code=e.submit(1,seq,accepted,input.data(),4096); if(code==0){++seq;accepted+=4096;} return code==RB_AUDIO_BACKPRESSURE; });
    check(e.status().source_accepted==accepted,"backpressure no consumption");
    until([&]{return e.status().primed!=0;}); check(e.play()==0,"primed play");
    check(e.pause()==0,"pause"); check(e.status().source_position==0,"pause frozen position");
    check(e.play()==0,"resume"); e.cancel();
    check(e.status().phase==RB_AUDIO_CANCELLED,"full queue cancel");
    check(e.finish(1,seq,accepted)==RB_AUDIO_STATE,"cancel eof rejected");
    StreamEngine underrun(descriptor(8192,48000),48000,128); check(underrun.start()==0,"underrun start");
    check(underrun.submit(1,0,0,input.data(),4096)==0,"prime input");
    until([&]{return underrun.status().primed!=0;}); check(underrun.play()==0,"underrun play");
    std::vector<float> out(8192); uint32_t actual=0;
    check(underrun.available(4096,actual)==0 && actual==4096,"prime available");
    check(underrun.consume(out.data(),4096)==0,"prime consume"); underrun.submitted(4096);
    check(underrun.available(1,actual)==RB_AUDIO_UNDERRUN,"starvation is fault");
    check(underrun.status().phase==RB_AUDIO_FAULT,"underrun phase");
}
void duration() {
    uint64_t result=0;
    check(rate_frame_bound(UINT64_MAX,192000,8000,result) && result==UINT64_MAX/24+1,"u64 downsample ceil");
    check(!rate_frame_bound(UINT64_MAX,8000,192000,result),"u64 upscale overflow");
    check(rate_frame_floor(UINT64_MAX,192000,8000,result) && result==UINT64_MAX/24,"u64 floor");
    auto d=descriptor(UINT64_C(192000)*86400,192000); StreamEngine e(d,192000,128); check(e.start()==0,"24h bounded admission");
    check(e.status().source_frames==d.source_frames && e.status().source_capacity==4096 && e.status().endpoint_total==0,"duration independent storage"); e.cancel();
    d=descriptor(1,192000); StreamEngine tiny(d,8000,128); check(tiny.start()==0,"tiny start");
    const float zero[2]{}; check(tiny.submit(1,0,0,zero,1)==0 && tiny.finish(1,1,1)==0,"tiny eof");
    until([&]{return tiny.status().result!=0;}); check(tiny.status().result==RB_AUDIO_RATE_EMPTY,"no synthetic short tail");
}
void identity_bits() {
    auto d=descriptor(4,48000); StreamEngine e(d,48000,128); check(e.start()==0,"identity start");
    const uint32_t bits[8]={0x80000000,1,0x80000001,0,0x00800000,0x80800000,0x3f800000,0xbf800000};
    float input[8]; std::memcpy(input,bits,sizeof(input));
    check(e.submit(1,0,0,input,4)==0 && e.finish(1,1,4)==0,"identity submit");
    until([&]{return e.status().primed!=0;}); check(e.play()==0,"short priming");
    uint32_t actual=0; float output[8]; check(e.available(128,actual)==0 && actual==4,"short terminal");
    check(e.consume(output,4)==0 && std::memcmp(input,output,sizeof(input))==0,"identity exact bits");
    e.submitted(4); check(e.status().source_position==0,"submission not position");
    check(e.observe(128) && e.status().source_position==4,"terminal padding completion");
    check(e.pause()==0 && e.status().phase==RB_AUDIO_FINISHED && e.status().source_position==4,"pause after exact completion preserves frozen end");
}
std::atomic<int> injected{0};
soxr_t create_injected(double a,double b,unsigned channels,soxr_error_t *error,const soxr_io_spec_t *io,const soxr_quality_spec_t *q,const soxr_runtime_spec_t *r) {
    if(injected.load()==1) { *error="authored create fault"; return nullptr; }
    return soxr_create(a,b,channels,error,io,q,r);
}
soxr_error_t process_injected(soxr_t soxr,soxr_in_t in,size_t ilen,size_t *idone,soxr_out_t out,size_t olen,size_t *odone) {
    *idone=0; *odone=0;
    if(injected.load()==2) return "authored process fault";
    if(injected.load()==3) return nullptr;
    if(injected.load()==4) { *odone=1; static_cast<float*>(out)[0]=INFINITY;static_cast<float*>(out)[1]=0;return nullptr; }
    if(injected.load()==5) { *odone=olen+1;return nullptr; }
    return soxr_process(soxr,in,ilen,idone,out,olen,odone);
}
std::vector<float> allocation_injected(size_t count) {
    if(injected.load()==6) throw std::bad_alloc();
    if(injected.load()==7) return {};
    return std::vector<float>(count);
}
void fault_controls() {
    const ConversionServices service{create_injected,process_injected,soxr_delete,allocation_injected};
    auto input=source(4096);
    for(int mode=1;mode<=7;++mode) {
        injected.store(mode);
        if(mode>=6) { bool rejected=false; try { StreamEngine e(descriptor(4096,48000),44100,128,&service); } catch(const std::bad_alloc&){rejected=true;} check(rejected,"allocation failure before admission");continue; }
        StreamEngine e(descriptor(4096,48000),44100,128,&service);
        const int result=e.start();
        if(mode==1) check(result==RB_AUDIO_CONVERSION,"create failure");
        else { check(result==0,"fault control start");check(e.submit(1,0,0,input.data(),4096)==0,"fault input");until([&]{return e.status().result!=0;});check(e.status().result==RB_AUDIO_CONVERSION,"process fault/no progress/nonfinite/overflow"); }
        check(e.status().phase==RB_AUDIO_FAULT,"fault phase");e.cancel();
    }
    for(int mode : {1,6,7}) {
        injected.store(mode); std::shared_ptr<StreamEngine> installed;
        const int code=create_stream_engine(descriptor(4096,48000),44100,128,installed,&service);
        check(code==(mode==1?RB_AUDIO_CONVERSION:RB_AUDIO_MEMORY) && !installed,"failed startup transfers no ownership");
    }
    injected.store(0);
    std::shared_ptr<StreamEngine> installed;
    check(create_stream_engine(descriptor(4096,48000),44100,128,installed,&service)==0 && installed,"successful startup transfers ownership");
    installed->cancel();installed.reset();
    struct Device {int stop=0,reset=0,stops=0,resets=0;};
    const auto stop=[](void*p)noexcept->StreamDeviceResult{auto*d=static_cast<Device*>(p);++d->stops;return{d->stop,d->stop ? -17 : 0};};
    const auto reset=[](void*p)noexcept->StreamDeviceResult{auto*d=static_cast<Device*>(p);++d->resets;return{d->reset,d->reset ? -23 : 0};};
    for(int which=0;which<2;++which) {
        StreamEngine e(descriptor(8192,48000),48000,128);check(e.start()==0,"device fault start");
        check(e.submit(1,0,0,input.data(),4096)==0,"device fault input");until([&]{return e.status().primed!=0;});check(e.play()==0,"device fault play");
        Device device{};if(which==0)device.stop=RB_AUDIO_DEVICE;else device.reset=RB_AUDIO_DEVICE;
        check(cancel_stream_device(e,&device,stop,reset)==RB_AUDIO_DEVICE,"stop/reset failure propagates");
        check(e.status().phase==RB_AUDIO_FAULT && e.status().result==RB_AUDIO_DEVICE,"failure is not stopped");
        check(e.submit(1,1,4096,input.data(),4096)==RB_AUDIO_STATE,"failure stops admission");
        if(which==0)check(device.resets==0,"failed stop never resets");
        device.stop=0;device.reset=0;check(cancel_stream_device(e,&device,stop,reset)==0,"cancel retry");
        check(e.status().phase==RB_AUDIO_CANCELLED && e.status().result==0,"successful retry clears fault");
    }
}
void concurrent_cancel() {
    auto input=source(4096);
    for(int cycle=0;cycle<40;++cycle) {
        StreamEngine e(descriptor(UINT64_C(192000)*86400,48000),cycle%2?44100:48000,128);check(e.start()==0,"race start");
        std::atomic<bool> done{false};std::atomic<bool> invalid{false};
        std::thread submitter([&]{uint64_t frames=0,seq=0;while(!done.load()) {
            const int code=e.submit(1,seq,frames,input.data(),4096);
            if(!code){frames+=4096;++seq;}else if(code==RB_AUDIO_STATE)break;else if(code!=RB_AUDIO_BACKPRESSURE){invalid.store(true);break;}
            std::this_thread::yield();
        }});
        if(cycle%3)until([&]{return e.status().primed!=0;});
        if(cycle%3==2){check(e.play()==0,"race play");check(e.pause()==0,"race pause");}
        e.cancel();done.store(true);submitter.join();
        const auto frozen=e.status();tick();const auto later=e.status();
        check(!invalid.load() && later.phase==RB_AUDIO_CANCELLED,"race barrier");
        check(frozen.source_accepted==later.source_accepted && frozen.endpoint_produced==later.endpoint_produced,"no late producer after barrier");
        check(later.source_peak<=4096 && later.endpoint_peak<=4096,"race bounded");
    }
}
void long_stream() {
    constexpr uint64_t frames=32004240;
    auto input=source(4096);std::array<float,8192> output{};
    StreamEngine e(descriptor(frames,32000,8192),32000,128);check(e.start()==0,"long start");
    uint64_t accepted=0,sequence=0,played=0,hash=UINT64_C(14695981039346656037),expected=hash;bool eof=false,playing=false;
    const auto started=std::chrono::steady_clock::now(), deadline=started+std::chrono::seconds(30);
    while(e.status().phase!=RB_AUDIO_FINISHED) {
        if(accepted<frames) {
            const uint32_t count=static_cast<uint32_t>(std::min<uint64_t>(4096,frames-accepted));
            const int code=e.submit(1,sequence,accepted,input.data(),count);check(code==0||code==RB_AUDIO_BACKPRESSURE,"long submit");
            if(!code){const auto*bytes=reinterpret_cast<const unsigned char*>(input.data());for(size_t i=0;i<size_t(count)*8;++i){expected^=bytes[i];expected*=UINT64_C(1099511628211);}accepted+=count;++sequence;}
        } else if(!eof){check(e.finish(1,sequence,accepted)==0,"long eof");eof=true;}
        auto s=e.status();check(s.result==0,"long healthy");
        if(s.primed&&!playing){check(e.play()==0,"long play");playing=true;}
        if(playing&&(s.endpoint_queued>=4096||s.endpoint_total_final)) {
            uint32_t actual=0;check(e.available(4096,actual)==0,"long available");
            if(actual){check(e.consume(output.data(),actual)==0,"long consume");e.submitted(actual);played+=actual;e.observe(played);
                const auto*bytes=reinterpret_cast<const unsigned char*>(output.data());for(size_t i=0;i<size_t(actual)*8;++i){hash^=bytes[i];hash*=UINT64_C(1099511628211);}}
        }
        if(playing)e.observe(played);
        if(std::chrono::steady_clock::now()>=deadline) {
            progress_report("long deadline",32000,32000,frames,4096,accepted,played,e.status(),started);
            check(false,"long deadline");
        }
        std::this_thread::yield();
    }
    check(played==frames&&hash==expected,"long incremental hash exactly matches submitted bytes");
    const auto s=e.status();check(s.source_peak<=8192&&s.endpoint_peak<=8192,"long bounded peaks");
    long_hash=hash;long_source_peak=s.source_peak;long_endpoint_peak=s.endpoint_peak;
    if(progress_diagnostics)progress_report("long completed",32000,32000,frames,4096,accepted,played,s,started);
}

void explicit_eof() {
    auto input=source(17);StreamEngine e(descriptor(17,48000),44100,128);check(e.start()==0,"EOF control start");
    check(e.submit(1,0,0,input.data(),17)==0,"EOF control input");
    until([&]{return e.status().source_consumed==17;});
    auto before=e.status();check(!before.source_eof&&!before.endpoint_total_final&&before.endpoint_total==0,"exhausted declared input is not EOF");
    check(before.endpoint_produced==0&&before.phase==RB_AUDIO_PRIMING,"zero-output converter progress is not finish");
    check(e.finish(1,1,17)==0,"explicit EOF accepted");until([&]{return e.status().endpoint_total_final!=0;});
    check(e.status().endpoint_total>0,"explicit EOF drains actual tail");
    check(e.finish(1,1,17)==RB_AUDIO_STATE,"duplicate EOF rejected");
}
void deferred_eof_clock() {
    auto input=source(4096);std::array<float,8192> output{};
    StreamEngine e(descriptor(4096,48000),48000,128);check(e.start()==0,"deferred EOF start");
    check(e.submit(1,0,0,input.data(),4096)==0,"deferred EOF submit");until([&]{return e.status().primed!=0;});
    check(e.play()==0,"deferred EOF play");uint32_t actual=0;check(e.available(4096,actual)==0&&actual==4096,"deferred EOF available");
    check(e.consume(output.data(),4096)==0,"deferred EOF consume");e.submitted(4096);
    check(!e.observe(4096)&&e.status().source_position==4095&&e.status().phase!=RB_AUDIO_FINISHED,"declared duration not premature EOF");
    check(e.finish(1,1,4096)==0,"deferred EOF finish");until([&]{return e.status().endpoint_total_final!=0;});
    check(e.observe(4096)&&e.status().source_position==4096,"final drain plus frozen device position completes");
}

void pause_final_race() {
    auto input=source(4096);
    for(int cycle=0;cycle<200;++cycle) {
        StreamEngine e(descriptor(4096,48000),48000,128);check(e.start()==0,"pause drain start");
        check(e.submit(1,0,0,input.data(),4096)==0,"pause drain submit");until([&]{return e.status().primed!=0;});
        check(e.play()==0,"pause drain play");check(e.finish(1,1,4096)==0,"pause drain finish");
        check(e.pause()==0,"pause accepts concurrent PLAYING to DRAINING");
        until([&]{return e.status().endpoint_total_final!=0;});
        check(e.status().phase==RB_AUDIO_PAUSED&&e.status().source_position==0,"producer completion never unpauses device");
        e.cancel();
    }
}

void maximum_block_ownership() {
    auto input=source(65536);const auto original=input;
    auto d=descriptor(65536,48000);d.source_queue_frames=65536;d.max_block_frames=65536;
    StreamEngine e(d,48000,128);check(e.start()==0,"maximum block start");
    check(e.submit(1,0,0,input.data(),65536)==0,"maximum block copied");
    std::fill(input.begin(),input.end(),0);check(e.finish(1,1,65536)==0,"maximum block EOF");
    until([&]{return e.status().primed!=0;});check(e.play()==0,"maximum block play");
    uint64_t read=0;std::array<float,8192> block{};
    while(e.status().phase!=RB_AUDIO_FINISHED) {
        auto state=e.status();check(valid_status(state)&&state.result==0,"maximum block state");
        if(state.endpoint_queued<4096&&!state.endpoint_total_final){tick();continue;}
        uint32_t actual=0;check(e.available(4096,actual)==0,"maximum block available");
        if(actual){check(e.consume(block.data(),actual)==0,"maximum block consume");
            check(std::memcmp(block.data(),original.data()+read*2,size_t(actual)*8)==0,"caller may release or mutate after accepted copy");
            e.submitted(actual);read+=actual;e.observe(read);}
        e.observe(read);
    }
    check(read==65536&&e.status().source_peak<=65536&&e.status().endpoint_peak<=4096,"maximum block bounded");
}

void concurrent_status() {
    auto input=source(17);
    for(int cycle=0;cycle<300;++cycle) {
        StreamEngine e(descriptor(17,48000),cycle%2?44100:48000,128);check(e.start()==0,"status start");
        std::atomic<bool> done{false}, invalid{false};
        std::thread observer([&]{while(!done.load()){if(!valid_status(e.status()))invalid.store(true);status_samples.fetch_add(1);std::this_thread::yield();}});
        check(e.submit(1,0,0,input.data(),17)==0 && e.finish(1,1,17)==0,"status admission");
        // Act immediately on the public admission flag. Sleeping through the
        // transition hides a producer publishing primed before READY.
        const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);
        while(!e.status().primed) {
            check(std::chrono::steady_clock::now()<deadline,"status priming deadline");
            std::this_thread::yield();
        }
        check(e.play()==0,"status play");uint32_t actual=0;float output[34]{};
        check(e.available(128,actual)==0 && actual<=17,"status terminal");
        check(e.consume(output,actual)==0,"status consume");e.submitted(actual);check(e.observe(actual),"status finished");
        e.cancel();done.store(true);observer.join();check(!invalid.load(),"concurrent completion publication coherent");
    }
    check(status_samples.load()>0,"status observer executed");
}

}
int main(int argc,char **argv) {
    // CTest retains completed stage diagnostics if a later control fails.
    // --json success output remains exactly the machine-readable receipt.
    progress_diagnostics=argc==1;
    protocol(); duration(); identity_bits(); fault_controls(); concurrent_cancel(); concurrent_status(); explicit_eof(); deferred_eof_clock(); pause_final_race(); maximum_block_ownership(); long_stream();
    const uint32_t ratios[][2]={{48000,48000},{48000,44100},{44100,48000},{32000,44100},{44100,32000},{8000,192000},{192000,8000}};
    for(const auto &r:ratios) for(uint32_t partition:{1u,257u,4096u}) exact(r[0],r[1],16403,partition,4096);
    for(const auto &r:ratios) exact(r[0],r[1],8193,997,8192);
    const std::string report="{\"schema\":\"rebase.native-bounded-stream-controls.v1\",\"status\":\"passed\",\"checks\":"+std::to_string(checks)+",\"oracle_cases\":28,\"status_race_cycles\":300,\"status_samples\":"+std::to_string(status_samples.load())+",\"cancel_race_cycles\":40,\"pause_final_race_cycles\":200,\"fault_injection_cases\":9,\"long_stream_frames\":32004240,\"long_fnv1a64\":\""+std::to_string(long_hash)+"\",\"long_source_peak_frames\":"+std::to_string(long_source_peak)+",\"long_endpoint_peak_frames\":"+std::to_string(long_endpoint_peak)+",\"duration_admission_frames\":16588800000,\"source_queue_bound_frames\":65536,\"endpoint_queue_bound_frames\":8192,\"fixed_pcm_storage_bound_bytes\":622592,\"max_pcm_storage_case\":{\"source_capacity_frames\":65536,\"endpoint_capacity_frames\":4096,\"rolling_input_frames\":4096,\"pending_output_frames\":4096,\"bytes\":622592},\"gates\":{\"snapshot_exact\":true,\"canonical_partitions\":true,\"coherent_status_publication\":true,\"identity_bits\":true,\"exact_eof\":true,\"zero_output_not_eof\":true,\"deferred_eof_clock_completion\":true,\"maximum_block_owned_copy\":true,\"bounded_backpressure\":true,\"starvation_fault\":true,\"u64_duration_mapping\":true,\"cancel_join_barrier\":true,\"pause_freezes_position\":true,\"pause_final_drain_race\":true,\"stop_reset_failure_retry\":true,\"converter_failures\":true,\"allocation_failures\":true,\"failed_startup_unpublished\":true,\"long_incremental_hash\":true},\"physical_playback_tested\":false}\n";
    if(argc==3&&std::strcmp(argv[1],"--json")==0){FILE*file=std::fopen(argv[2],"wb");if(!file)return 2;const auto written=std::fwrite(report.data(),1,report.size(),file);const int closed=std::fclose(file);if(written!=report.size()||closed)return 2;}
    else if(argc!=1)return 2;
    std::fwrite(report.data(),1,report.size(),stdout);
}

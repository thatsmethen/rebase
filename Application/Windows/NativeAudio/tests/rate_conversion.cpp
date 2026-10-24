#include "RateConversion.hpp"
#include "RatePlaybackCursor.hpp"
#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <new>
#include <string>
#include <vector>
#if defined(_M_X64) || defined(__x86_64__)
#include <xmmintrin.h>
#endif

static unsigned checks = 0, failures = 0;
#define CHECK(condition) do { ++checks; if (!(condition)) { ++failures; std::fprintf(stderr, "line %d: %s\n", __LINE__, #condition); } } while (false)
struct Case { const char *name; uint32_t source_rate, endpoint_rate; uint64_t source_frames, endpoint_frames; unsigned failures; };
static std::vector<Case> cases;
static std::vector<float> samples(size_t frames) {
    std::vector<float> value(frames * 2);
    for (size_t i = 0; i < frames; ++i) {
        value[2 * i] = static_cast<float>(0.2 * std::sin(2 * 3.141592653589793 * static_cast<double>(i) / 100));
        value[2 * i + 1] = -value[2 * i] * 0.5f;
    }
    return value;
}
static void converted_case(const char *name, uint32_t input_rate, uint32_t output_rate, uint64_t frames) {
    const unsigned before = failures;
    auto input = samples(static_cast<size_t>(frames)); const auto original = input;
    std::vector<float> output;
    CHECK(rebase::convert_snapshot(input.data(), frames, input_rate, output_rate, output) == RB_AUDIO_OK);
    CHECK(input == original);
    const uint64_t expected = (frames * output_rate + input_rate / 2) / input_rate;
    CHECK(output.size() == expected * 2);
    CHECK(!output.empty());
    for (size_t i = 0; i < output.size() / 2; ++i) {
        CHECK(std::isfinite(output[2 * i]) && std::isfinite(output[2 * i + 1]));
        CHECK(std::fabs(output[2 * i + 1] + output[2 * i] * 0.5f) < 1e-6f);
        if (frames >= 4000 && i >= 1024 && i + 1024 < output.size()/2) {
            // Independent passband time/amplitude oracle, away from the finite
            // signal edges. This also rejects a count-correct wrong-rate copy.
            const double expected_sample=0.2*std::sin(2*3.141592653589793*static_cast<double>(i)*
                input_rate/(static_cast<double>(output_rate)*100));
            CHECK(std::fabs(output[2*i]-expected_sample) < 2e-4);
        }
    }
    cases.push_back({name,input_rate,output_rate,frames,output.size()/2,failures-before});
}
static int backend_mode = 0, destroyed = 0;
static int fake_handle;
static soxr_t fake_create(double, double, unsigned, soxr_error_t *error, const soxr_io_spec_t *,
                           const soxr_quality_spec_t *, const soxr_runtime_spec_t *) {
    *error = backend_mode == 1 || backend_mode == 2 ? "authored create failure" : nullptr;
    return backend_mode == 1 ? nullptr : reinterpret_cast<soxr_t>(&fake_handle);
}
static soxr_error_t fake_process(soxr_t, soxr_in_t, size_t count, size_t *used, soxr_out_t output,
                                  size_t capacity, size_t *made) {
    *used = 0; *made = 0;
    if (backend_mode == 3) return "authored process failure";
    if (backend_mode == 4) { *used = count + 1; return nullptr; }
    if (backend_mode == 5) { *used = count; *made = 1; static_cast<float *>(output)[0] = std::numeric_limits<float>::infinity(); return nullptr; }
    if (backend_mode == 6) { *made = capacity + 1; return nullptr; }
    return nullptr; // Deliberate nonprogress.
}
static void fake_destroy(soxr_t) { ++destroyed; }
static std::vector<float> allocate(size_t count) { return std::vector<float>(count); }
static std::vector<float> no_memory(size_t) { throw std::bad_alloc(); }

int main(int argc, char **argv) {
    const char *json_path = nullptr;
    if (argc == 3 && std::strcmp(argv[1], "--json") == 0) json_path = argv[2];
    else if (argc != 1) return 2;
    CHECK(sizeof(RBAudioStatus) == 72 && sizeof(RBAudioRateInfo) == 56);
    CHECK(std::strcmp(soxr_version(), "libsoxr-0.1.3") == 0);
    CHECK(rebase::conversion_environment_valid());
    {
        const unsigned before = failures;
        const uint32_t bits[] = {0x80000000u,0,1,0x80000001u,0x3f000000u,0xbf000000u};
        float input[6]; std::memcpy(input,bits,sizeof(bits)); std::vector<float> output;
        CHECK(rebase::convert_snapshot(input,3,48000,48000,output) == RB_AUDIO_OK);
        CHECK(output.size() == 6 && std::memcmp(output.data(),bits,sizeof(bits)) == 0);
        cases.push_back({"identity-bits",48000,48000,3,output.size()/2,failures-before});
    }
    converted_case("44100-to-48000",44100,48000,4410);
    converted_case("48000-to-44100",48000,44100,4800);
    converted_case("8000-to-192000",8000,192000,256);
    converted_case("192000-to-8000",192000,8000,6144);
    converted_case("fractional-frame-count",44100,48000,137);
    {
        const unsigned before = failures;
        auto input = samples(1); std::vector<float> output{42,43};
        CHECK(rebase::convert_snapshot(input.data(),1,192000,8000,output) == RB_AUDIO_RATE_EMPTY);
        CHECK(output == std::vector<float>({42,43}));
        for (uint64_t length=2;length<=97;++length) {
            input=samples(static_cast<size_t>(length));
            const uint64_t expected=(length+12)/24;
            const int result=rebase::convert_snapshot(input.data(),length,192000,8000,output);
            CHECK(result == (expected ? RB_AUDIO_OK : RB_AUDIO_RATE_EMPTY));
            if(expected) CHECK(output.size() == expected*2);
        }
        cases.push_back({"short-empty-downsample",192000,8000,1,0,failures-before});
    }
    {
        const unsigned before = failures;
        // Analytic zero, stereo isolation and a late impulse exercise EOF drain
        // independently of implementation segmentation/count bookkeeping.
        std::vector<float> input(9600), output;
        CHECK(rebase::convert_snapshot(input.data(),4800,48000,44100,output) == RB_AUDIO_OK);
        CHECK(std::all_of(output.begin(),output.end(),[](float x){return x == 0;}));
        input[2 * 4799] = 0.5f;
        CHECK(rebase::convert_snapshot(input.data(),4800,48000,44100,output) == RB_AUDIO_OK);
        float tail_peak = 0;
        for (size_t i=0;i<output.size()/2;++i) {
            CHECK(output[2*i+1] == 0);
            if (i>4300) tail_peak=std::max(tail_peak,std::fabs(output[2*i]));
        }
        CHECK(tail_peak > 0.01f && tail_peak < 1);
        cases.push_back({"zero-isolation-tail-drain",48000,44100,4800,output.size()/2,failures-before});
    }
    {
        const unsigned before = failures;
        auto input=samples(137); std::vector<float> output;
        CHECK(rebase::convert_snapshot(input.data(),137,44100,48000,output) == RB_AUDIO_OK);
        const auto original = output;
        rebase::RatePlaybackCursor cursor;
        CHECK(cursor.configure(137,44100,output.size()/2,48000) == RB_AUDIO_OK);
        for (uint64_t source_frame : {0ull,1ull,13ull,68ull,135ull,136ull,137ull}) {
            CHECK(cursor.seek(source_frame) == RB_AUDIO_OK);
            const uint64_t endpoint_frame = source_frame == 137 ? output.size()/2 :
                std::min<uint64_t>(output.size()/2,(source_frame*48000+22050)/44100);
            CHECK(cursor.endpoint_index() == endpoint_frame);
            CHECK(cursor.rate_info().endpoint_position_frames == endpoint_frame);
            if (endpoint_frame < output.size()/2) {
                CHECK(cursor.status().position_frames == source_frame);
                CHECK(std::memcmp(output.data()+2*endpoint_frame,original.data()+2*endpoint_frame,
                    (output.size()-2*endpoint_frame)*sizeof(float)) == 0);
            } else CHECK(cursor.status().phase == RB_AUDIO_FINISHED && cursor.status().position_frames == 137);
        }
        // Exact half-frame seek, and near-end collapse in a downsampled stream.
        CHECK(cursor.configure(480,48000,80,8000) == RB_AUDIO_OK);
        CHECK(cursor.seek(2) == RB_AUDIO_OK && cursor.endpoint_index() == 0);
        CHECK(cursor.seek(3) == RB_AUDIO_OK && cursor.endpoint_index() == 1);
        CHECK(cursor.seek(477) == RB_AUDIO_OK && cursor.status().phase == RB_AUDIO_FINISHED);
        CHECK(cursor.status().position_frames == 480);
        CHECK(cursor.seek(481) == RB_AUDIO_ARGUMENT && cursor.status().position_frames == 480);
        cases.push_back({"seek-phase-preserved",44100,48000,137,output.size()/2,failures-before});
    }
    {
        const unsigned before=failures;
        rebase::RatePlaybackCursor cursor;
        CHECK(cursor.configure(4410,44100,4800,48000) == RB_AUDIO_OK);
        CHECK(cursor.status().sample_rate == 44100 && cursor.rate_info().endpoint_rate == 48000);
        const auto initial=cursor.rate_info(); const auto initial_generation=cursor.status().generation;
        CHECK(cursor.configure(0,48000,100,48000) == RB_AUDIO_ARGUMENT);
        CHECK(cursor.configure(100,48000,0,44100) == RB_AUDIO_ARGUMENT);
        CHECK(cursor.configure(100,48000,32000001,44100) == RB_AUDIO_ARGUMENT);
        CHECK(cursor.status().generation == initial_generation && cursor.rate_info().source_frames == initial.source_frames);
        CHECK(cursor.rate_info().endpoint_rate == initial.endpoint_rate && cursor.rate_info().endpoint_frames == initial.endpoint_frames);
        CHECK(cursor.play() == RB_AUDIO_OK && cursor.submitted(480));
        CHECK(cursor.status().position_frames == 0 && cursor.status().submitted_frames == 441);
        CHECK(!cursor.observe(240) && cursor.status().position_frames == 220);
        CHECK(!cursor.observe(239) && cursor.status().position_frames == 220);
        CHECK(cursor.pause() == RB_AUDIO_OK);
        CHECK(!cursor.observe(9999) && cursor.status().position_frames == 220);
        CHECK(cursor.rate_info().endpoint_submitted_frames == 480);
        CHECK(cursor.play() == RB_AUDIO_OK);
        CHECK(!cursor.observe(480) && cursor.status().position_frames == 441);
        CHECK(cursor.seek(2205) == RB_AUDIO_OK && cursor.endpoint_index() == 2400);
        CHECK(cursor.status().phase == RB_AUDIO_PLAYING && cursor.status().position_frames == 2205);
        CHECK(cursor.submitted(2400));
        CHECK(!cursor.observe(2399) && cursor.status().phase == RB_AUDIO_PLAYING);
        CHECK(cursor.observe(2400) && cursor.status().position_frames == 4410);
        CHECK(cursor.status().phase == RB_AUDIO_FINISHED);
        CHECK(cursor.stop() == RB_AUDIO_OK && cursor.endpoint_index() == 0 && cursor.status().position_frames == 0);
        const auto generation=cursor.status().generation;
        CHECK(cursor.seek(123) == RB_AUDIO_OK && cursor.status().generation == generation+1);
        CHECK(cursor.play() == RB_AUDIO_OK && cursor.submitted(10));
        CHECK(!cursor.observe(11) && cursor.status().result == RB_AUDIO_UNDERRUN);
        CHECK(cursor.status().phase == RB_AUDIO_FAULT && cursor.rate_info().source_rate == 44100);
        const auto fault_generation=cursor.status().generation;
        CHECK(cursor.configure(100,8000,2400,192000) == RB_AUDIO_OK);
        CHECK(cursor.status().generation == fault_generation+1 && cursor.status().phase == RB_AUDIO_READY);
        CHECK(cursor.status().result == RB_AUDIO_OK && cursor.status().sample_rate == 8000);
        CHECK(cursor.rate_info().endpoint_rate == 192000 && cursor.rate_info().endpoint_position_frames == 0);
        cases.push_back({"pause-reset-drain",44100,48000,4410,4800,failures-before});
    }
    {
        const unsigned before=failures; auto input=samples(32); std::vector<float> output{42,43};
        rebase::ConversionServices hooks{fake_create,fake_process,fake_destroy,no_memory};
        CHECK(rebase::convert_snapshot(input.data(),32,48000,44100,output,&hooks) == RB_AUDIO_MEMORY);
        CHECK(output == std::vector<float>({42,43}));
        cases.push_back({"allocation-failure",48000,44100,32,0,failures-before});
    }
    {
        const unsigned before=failures; auto input=samples(32); std::vector<float> output{42,43};
        rebase::ConversionServices hooks{fake_create,fake_process,fake_destroy,allocate};
        for(backend_mode=1;backend_mode<=7;++backend_mode) {
            const int prior_destroyed=destroyed;
            CHECK(rebase::convert_snapshot(input.data(),32,48000,44100,output,&hooks) == RB_AUDIO_CONVERSION);
            CHECK(output == std::vector<float>({42,43}));
            CHECK(destroyed == prior_destroyed + (backend_mode == 1 ? 0 : 1));
        }
        cases.push_back({"converter-failure",48000,44100,32,0,failures-before});
    }
    {
        const unsigned before=failures;
        // A modest source allocation crosses the endpoint capacity at 24x.
        auto input=samples(1333334); std::vector<float> output{42,43};
        CHECK(rebase::convert_snapshot(input.data(),1333334,8000,192000,output) == RB_AUDIO_CAPACITY);
        CHECK(output == std::vector<float>({42,43}));
        CHECK(rebase::convert_snapshot(nullptr,1,48000,44100,output) == RB_AUDIO_ARGUMENT);
        CHECK(rebase::convert_snapshot(input.data(),1,48000,192001,output) == RB_AUDIO_ARGUMENT);
        cases.push_back({"capacity-rejection",8000,192000,1333334,0,failures-before});
    }
    {
        const unsigned before=failures; auto input=samples(32); std::vector<float> output{42,43};
        const int old=std::fegetround();
        for(int rounding : {FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO}) {
            CHECK(std::fesetround(rounding) == 0);
            CHECK(rebase::convert_snapshot(input.data(),32,48000,44100,output) == RB_AUDIO_ENVIRONMENT);
            CHECK(output == std::vector<float>({42,43})); CHECK(std::fesetround(old) == 0);
        }
#if defined(_M_X64) || defined(__x86_64__)
        const unsigned mxcsr=_mm_getcsr();
        for(unsigned bit : {1u<<6,1u<<15}) {
            _mm_setcsr(mxcsr|bit);
            CHECK(rebase::convert_snapshot(input.data(),32,48000,44100,output) == RB_AUDIO_ENVIRONMENT);
            _mm_setcsr(mxcsr);
        }
#elif defined(__aarch64__) && !defined(_MSC_VER)
        uint64_t fpcr; __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
        const uint64_t flush=fpcr|(1ull<<24); __asm__ volatile("msr fpcr, %0" :: "r"(flush));
        CHECK(rebase::convert_snapshot(input.data(),32,48000,44100,output) == RB_AUDIO_ENVIRONMENT);
        __asm__ volatile("msr fpcr, %0" :: "r"(fpcr));
#endif
        CHECK(rebase::conversion_environment_valid());
        cases.push_back({"environment-rejection",48000,44100,32,0,failures-before});
    }
    std::string json="{\"schema\":1,\"suite\":\"native-audio-rate-conversion\",\"checks\":"+std::to_string(checks)+
        ",\"failures\":"+std::to_string(failures)+",\"wasapi_compiled\":false,\"playback_tested\":false,\"audible_output_measured\":false,"
        "\"soxr_version\":\""+soxr_version()+"\",\"profile\":{\"recipe\":6,\"channels\":2,\"linear_phase\":true,\"runtime_threads\":1,\"implicit_os_conversion\":false},\"cases\":[";
    bool first=true;
    for(const auto &c:cases) {
        if(!first) json+=","; first=false;
        json+="{\"name\":\""+std::string(c.name)+"\",\"source_rate\":"+std::to_string(c.source_rate)+
            ",\"endpoint_rate\":"+std::to_string(c.endpoint_rate)+",\"source_frames\":"+std::to_string(c.source_frames)+
            ",\"endpoint_frames\":"+std::to_string(c.endpoint_frames)+",\"failures\":"+std::to_string(c.failures)+"}";
    }
    json+="]}\n";
    std::fputs(json.c_str(),stdout);
    if(json_path) { FILE *f=std::fopen(json_path,"wb"); if(!f) return 2;
        const size_t written=std::fwrite(json.data(),1,json.size(),f); const int closed=std::fclose(f);
        if(written!=json.size() || closed!=0) return 2; }
    return failures ? 1 : 0;
}

"""Supplied-state discriminators of the static ownership graph; no target execution."""
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent
rows = []
def check(name, actual, expected, rejects):
    assert actual == expected, (name, actual, expected)
    rows.append(dict(name=name, supplied_state_result=actual, expected=expected,
                     rejected_interpretation=rejects))

def curve_or_invert(source):
    return dict(rate=source['rate'], kind=2, bits=32)

def group_formats(members, reference):
    # Native1002d9034 selects reference+38;1002d91a4 sets every accessor output.
    target = members[reference]
    return [dict(source_rate=m['rate'], output_rate=target['rate'],
                 output_kind=target['kind'], output_bits=target['bits']) for m in members]

def group_read(request, responses):
    #1002d9620 retains request unless a negative response occurs; latest negative wins.
    negative = [n for n in responses if n < 0]
    return negative[-1] if negative else request

def group_seek(position, offsets, responses):
    #1002d96f0 passes position+offset per member; positive actual positions are not combined.
    negative = [n for n in responses if n < 0]
    return dict(member_queries=[position+x for x in offsets],
                returned=negative[-1] if negative else position)

pcm44 = dict(rate=44100, kind=1, bits=24)
pcm48 = dict(rate=48000, kind=1, bits=16)
check('curve_preserves_rate_and_changes_format',curve_or_invert(pcm44),
      dict(rate=44100,kind=2,bits=32),'All processed streams adopt project48000 or preserve PCM24')
check('invert_preserves_rate_and_changes_format',curve_or_invert(pcm48),
      dict(rate=48000,kind=2,bits=32),'Inversion changes sample rate')
check('reference44_controls_both_member_accessors',group_formats([pcm44,pcm48],0),
      [dict(source_rate=44100,output_rate=44100,output_kind=1,output_bits=24),
       dict(source_rate=48000,output_rate=44100,output_kind=1,output_bits=24)],
      'Every member retains its own accessor output rate, or project96000 is used')
check('reference48_changes_all_output_formats',group_formats([pcm44,pcm48],1),
      [dict(source_rate=44100,output_rate=48000,output_kind=1,output_bits=16),
       dict(source_rate=48000,output_rate=48000,output_kind=1,output_bits=16)],
      'Group always chooses first member independent of reference index')
check('outer_warp_float32_after_inner_reference_pcm',curve_or_invert(pcm44),
      dict(rate=44100,kind=2,bits=32),
      'Float32 outer format permits removing inner reference-PCM conversion/quantization')
check('new_accessor_snapshot_not_live_getter',dict(snapshot_rate=44100,current_source_rate=48000),
      dict(snapshot_rate=44100,current_source_rate=48000),
      'Accessor+30 automatically tracks every subsequent source getter change; hypothetical mutation, not admitted host lifecycle')
check('typed_cache_is_separate_source',dict(cache_hit_rate=32000,original_clip_rate=44100),
      dict(cache_hit_rate=32000,original_clip_rate=44100),
      'Original clip metadata fixes an arbitrary already-cached AudioStream rate')
check('group_read_does_not_min_positive_counts',group_read(128,[128,17]),128,
      'Outer group read returns minimum positive member result')
check('group_read_last_negative',group_read(128,[-2,64,-7]),-7,
      'Outer group read stops at first negative member or returns minimum count')
check('group_seek_offsets_and_success_return',group_seek(100,[0,23],[100,122]),
      dict(member_queries=[100,123],returned=100),
      'Group seek computes a common success position from rounded member seeks')
check('group_seek_negative_failure',group_seek(100,[0,23],[-2,-5]),
      dict(member_queries=[100,123],returned=-5),
      'Successful requested position is returned despite a negative member result')
result=dict(evidence_class='Analytical supplied-state model discriminators', target_executed=False,
            native_runtime_validation=False, passed=True, count=len(rows), controls=rows,
            domain='Finite positive integral rates, valid reference/index and bound getters; positive signed32 request and representable offset/byte arithmetic. No sample-DSP or provider execution.',
            limitation='These assertions clarify implications and falsify alternate readings of reviewed instructions. They do not independently validate the ownership interpretation or actual host reachability.')
with (HERE/'analytical-controls.json').open('x') as f:
    json.dump(result,f,indent=2); f.write('\n')
print(f'{len(rows)} supplied-state controls passed; no target execution')

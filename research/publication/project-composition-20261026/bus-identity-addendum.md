# Saved bus identity receiver closure — additive continuation

This continues `finding.md` without changing the 58-function record. `verification-continued-01.json` now verifies 86 original-address derivatives and 86 REA readbacks, plus the same 21 iterator slots. All reference work is static. The target pin remains dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb. No target program ran.

## Exact receiver chain

- Owner constructor 101dc760c calls in-place VSTBusCollection constructor 101d4d664 at owner+950 (call 101dc784c), then publishes that owner to global105010970 at101dc7b58. The collection table1047adad0 is installed by101d4d664. VSTBusValue's captured global-owner+950 pointer therefore has a concrete collection receiver.
- Bus constructor101f017e0 calls101f16728→101ef2ccc. The base creates a24-byte adapter, installs1047e01f0, stores the bus at adapter+10 and the adapter at bus+8. Bus constructor installs1047e3768 and obtains its runtimeID from a global incrementing counter at104fa4cb0, storing it at+220. Getter10045b334 consists of exactly `ldr w0,[x0,#220];ret`; its larger LC_FUNCTION_STARTS interval contains unrelated following code and is not claimed as its reachable body.
- Adapter attribute reader+ b0 is101ee9d10. It retrieves the owner, constructs visitor1047e8488 and calls owner+b0. The concrete bus dispatcher10045b2d0 calls visitor+20, whose cell selects101f2e314. That method directly calls101f30b34 and stores its success byte. The serialized-adapter visitor is distinct:101ee9c70→1047e8300+20→101f2d910→101f30360. No equivalence between those reader formats is inferred.
- Attribute reader101f30b34 reads signed integer `Bus UID` (string1038f1488), defaulting its local storage to0. Only nonzero values call100dbf31c on map104f9bef0 with the savedID and address of bus+220. It separately reads `Bus Type` (1038f1450), restores speaker configurations and processes `Child Bus` (1038f147e); invalid/incompatible children may be removed. The saved child list alone does not guarantee the final runtime child set.
- Map setter100dbf31c requires an enabled restoration context and active map+68. It inserts/updates saved signed32 key→current signed32 value and delivers that value to registered callbacks. VSTBusValue callback101d62c14 writes its selector+3c. Immediate and deferred restoration are covered by these two halves. Registry lookup101d4d748 compares the same virtual+1b8 getter, parent before direct children, before next parent. It does not interpret saved IDs as root ordinals or names.

## Corrections and boundaries

The exploratory label `bus-collection-copy684` was wrong:101d4d684 destroys/frees the collection vector. Original exploratory records remain unchanged. Post-restore101d694a8 propagates name-like state into folders and panner; it is not evidence of audio routing or summation.

Channel restore101d75bcc does not apply OutputBusValue unconditionally. At101d766c8..101d76708 it requires an existing nested field, successful nonzero Value extraction, and an additional restoration-option branch. OutputBus and RecorderBus receivers have further channel-type/option branches. The decoder must distinguish raw saved selector evidence from an effective restored route.

The executable boundary is a source-bound read-only root/association/state decoder and saved-UID candidate graph. Runtime registry population from the entire project, the selected channel receiver, restoration options, child compatibility pruning, mute/solo/monitor/automation, panner and processing neutrality, and engine mix accumulation remain unresolved. There is still no proved full-project audio admission domain.

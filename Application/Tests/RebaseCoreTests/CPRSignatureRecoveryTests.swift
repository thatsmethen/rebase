import Foundation
import Testing
@testable import RebaseCore

/// All generated controls are self-authored, not Reference runtime outputs.
final class CPRSignatureRecoveryTests {
    private func u16(_ x: UInt16) -> Data { var x=x.bigEndian; return withUnsafeBytes(of: &x) { Data($0) } }
    private func u32(_ x: UInt32) -> Data { var x=x.bigEndian; return withUnsafeBytes(of: &x) { Data($0) } }
    private func u64(_ x: UInt64) -> Data { var x=x.bigEndian; return withUnsafeBytes(of: &x) { Data($0) } }
    private func string(_ s: String) -> Data { u32(UInt32(s.utf8.count+1))+Data(s.utf8)+Data([0]) }
    private func object(_ name: String, _ version: UInt16 = 0, _ body: Data) -> Data {
        u32(.max)+string(name)+u16(version)+u32(UInt32(body.count))+body
    }
    private func field(_ key: String, _ type: UInt16, _ value: Data) -> Data { string(key)+u16(type)+value }
    private func integer(_ key: String, _ value: Int64) -> Data { field(key,1,u64(UInt64(bitPattern:value))) }
    private func number(_ key: String, _ value: Double) -> Data { field(key,4,u64(value.bitPattern)) }
    private func fields(_ items: [Data]) -> Data { u32(UInt32(items.count))+items.reduce(Data(),+) }
    private func defaults(bar: Int64? = 0, numerator: Int64 = 7, denominator: Int64 = 8, position: Int64 = 0) -> [Data] {
        var values = [integer("Flags",8),number("Start",0),number("Length",1)]
        if let bar { values.append(integer("Bar",bar)) }
        values += [integer("Numerator",numerator),integer("Denominator",denominator),integer("Position",position)]
        return values
    }
    private func typed(_ values: [Data], name: String = "MTimeSignatureEvent", items: UInt32 = 1) -> Data {
        let item = u16(20)+string(name)+u64(0x123456789abcdef0)+fields(values)
        let array = field("SignatureEvent",2,u16(201)+u32(items)+item)
        return object("FAttributes",0,fields([array]))
    }
    private func variation(alternate: Data? = nil, selector: UInt32 = 0, flags: UInt16 = 2,
                           count: UInt32 = 1, version: UInt16 = 0) -> Data {
        let child = object("MTrackVariation",version,string("v1")+(alternate ?? u32(0))+u32(selector))
        return object("MTrackVariationCollection",0,u32(10)+u16(flags)+u32(count)+child)
    }
    private func signature(_ values: [Data]? = nil, typedOverride: Data? = nil,
                           variation: Data? = nil, compactCount: UInt32 = 1,
                           compactNumerator: UInt16 = 7, compactDenominator: UInt16 = 8,
                           trailing: Data = Data(), duplicateKey: Bool = false) -> Data {
        let compact = u32(compactCount)+u32(0)+u16(compactNumerator)+u16(compactDenominator)+u16(0)+u16(0)+u16(0)+u16(8)
        var attrs: [Data] = [u32(0x53636f4c)+u16(1)+u64(0)]
        if let variation { attrs.append(u32(0x69435654)+u16(0x22)+variation) }
        attrs.append(u32(0x736b6c43)+u16(2)+(typedOverride ?? typed(values ?? defaults())))
        if duplicateKey { attrs.append(u32(0x53636f4c)+u16(1)+u64(0)) }
        return object("MSignatureTrackEvent",3,compact+fields(attrs)+trailing)
    }
    private func tempo() -> Data {
        object("MTempoTrackEvent",3,u32(1)+u32(Float(0.5).bitPattern)+u64(0)+u64(0)+u16(0)+u32(Float(120).bitPattern)+u16(1))
    }
    private func envelope(second: Data, first: Data? = nil, nested: Data = Data()) -> Data {
        let node = object("MTrackList",0,string("")+u32(0)+(first ?? tempo())+second+u16(0)+u32(nested.isEmpty ? 0:1)+nested)
        let root = object("MRoot",6,Data(repeating:0,count:26)+node)
        let archive = object("PArrangement",4,root)
        func rawString(_ s:String)->Data { u32(UInt32(s.utf8.count))+Data(s.utf8) }
        func chunk(_ tag:String,_ bytes:Data)->Data { Data(tag.utf8)+u32(UInt32(bytes.count))+bytes }
        let sections = chunk("ROOT",rawString("Arrangement1")+rawString("PArrangement"))+chunk("ARCH",archive)
        return Data("RIFF".utf8)+u32(UInt32(sections.count))+Data("NUND".utf8)+sections
    }
    private func recover(_ bytes: Data) throws -> CPRSignatureRecoveryResult {
        try CPRSignatureRecovery.recover(container: CPRProject.readContainer(bytes))
    }
    private func rejects(_ bytes: Data) {
        do { #expect(try recover(bytes).signature == nil) }
        catch { /* Malformed input is also an explicit rejection. */ }
    }

    @Test func matchingRepresentationsRecoverAndNamedBarIgnoresPosition() throws {
        let bytes = envelope(second: signature(defaults(position: 1920)))
        let recovered = try recover(bytes)
        #expect(recovered.signature?.beat == 0)
        #expect(recovered.signature?.numerator == 7 && recovered.signature?.denominator == 8)
        #expect(recovered.signature?.id == (try recover(bytes).signature?.id))
        #expect(recovered.facts.contains { $0.contains("Compact and typed representations agree") })
        #expect(recovered.objects.contains { $0.className == "MSignatureTrackEvent" })
    }

    @Test func missingPairedRoleCannotPromoteAnUnrelatedSignature() throws {
        let sig = signature()
        let absent = try recover(envelope(second: u32(0), nested: sig))
        #expect(absent.signature == nil && !absent.unsupported.isEmpty)
        let wrongRole = try recover(envelope(second: u32(0), first: sig))
        #expect(wrongRole.signature == nil)
        // Counted opaque child descriptors are retained as visited evidence,
        // but they do not supply the missing interface role or recovery fact.
        #expect(absent.objects.contains { $0.className == "MSignatureTrackEvent" })
        #expect(absent.facts.isEmpty)
        rejects(envelope(second:sig,first:sig))
        rejects(envelope(second:sig,first:object("UnknownTempoInterface",0,Data())))
    }

    @Test func explicitOriginAndExactIntegerTypesAreRequired() {
        rejects(envelope(second: signature(defaults(bar:nil))))
        rejects(envelope(second: signature(defaults(bar:1))))
        rejects(envelope(second: signature(defaults(numerator:65543))))
        rejects(envelope(second: signature(defaults(denominator:3))))
        var missing = defaults(); missing.remove(at:4)
        rejects(envelope(second: signature(missing)))
        var coerced = defaults(); coerced[4] = number("Numerator",7)
        rejects(envelope(second: signature(coerced)))
        var position = defaults(); position[position.count-1] = number("Position",0)
        rejects(envelope(second: signature(position)))
    }

    @Test func duplicateKeysAndMalformedExtentsAreNeverDefaults() {
        rejects(envelope(second: signature(defaults()+[integer("Bar",0)])))
        rejects(envelope(second: signature(duplicateKey:true)))
        rejects(envelope(second: signature(compactCount:0)))
        rejects(envelope(second: signature(compactCount:.max)))
        rejects(envelope(second: signature(trailing:Data([0]))))
        rejects(envelope(second: signature(typedOverride:typed(defaults(),items:2))))
        let bytes = envelope(second: signature())
        for end in stride(from:12,to:bytes.count,by:19) { rejects(Data(bytes.prefix(end))) }
    }

    @Test func noTypedContainerOrWrongClassCannotBecomeCompactRecovery() {
        rejects(envelope(second:signature(typedOverride:u32(0))))
        rejects(envelope(second:signature(typedOverride:typed(defaults(),name:"MTempoEvent"))))
        rejects(envelope(second:signature(typedOverride:typed(defaults(),name:"\u{feff}MTimeSignatureEvent"))))
    }

    @Test func contradictoryCompactAndTypedStateIsNotPromotedAcrossUnknownCompatibility() {
        rejects(envelope(second:signature(compactNumerator:4,compactDenominator:4)))
    }

    @Test func differentConcreteTrackPairsCannotBeMergedAndNonTrackObjectsDoNotSupplyRoles() throws {
        let nestedNode = object("MListNode",0,string("Track")+u32(0)+tempo()+signature()+u32(0))
        let nestedTrack = object("MAudioTrackEvent",1,Data(repeating:0,count:26)+nestedNode)
        rejects(envelope(second:signature(),nested:nestedTrack))
        let ignored = signature(defaults(numerator:3,denominator:4),compactNumerator:3,compactDenominator:4)
        let result = try recover(envelope(second:signature(),nested:ignored))
        #expect(result.signature?.numerator == 7 && result.signature?.denominator == 8)
    }

    @Test func nullCounterpartsRemainExplicitWithoutInventingTheMissingClock() throws {
        let signatureOnly = envelope(second:signature(),first:u32(0))
        let signatureRoles = try CPRClockRoles.resolve(container:CPRProject.readContainer(signatureOnly))
        #expect(signatureRoles.tempo == nil && signatureRoles.signature != nil)
        #expect(signatureRoles.pairedNodeCount == 1 && signatureRoles.trackNodeCount == 1)
        #expect(try recover(signatureOnly).signature?.numerator == 7)
        let tempoOnly = envelope(second:u32(0))
        let tempoRoles = try CPRClockRoles.resolve(container:CPRProject.readContainer(tempoOnly))
        #expect(tempoRoles.tempo != nil && tempoRoles.signature == nil)
        #expect(try recover(tempoOnly).signature == nil)
    }

    @Test func nullAlternateVariationIsAcceptedButOtherStatesAreExplicitlyGated() throws {
        let supported = try recover(envelope(second:signature(variation:variation())))
        #expect(supported.signature?.numerator == 7)
        let alternate = object("MDataNode",0,Data())
        rejects(envelope(second:signature(variation:variation(alternate:alternate))))
        rejects(envelope(second:signature(variation:variation(selector:1))))
        rejects(envelope(second:signature(variation:variation(flags:0))))
        rejects(envelope(second:signature(variation:variation(count:2))))
        rejects(envelope(second:signature(variation:variation(version:1))))
    }

    @Test func unknownOrCompoundSignatureExtrasAreNotSilentlyRecovered() {
        rejects(envelope(second:signature(defaults()+[integer("Mystery",1)])))
        rejects(envelope(second:signature(defaults()+[integer("SubNumerator1",3)])))
        rejects(envelope(second:signature(defaults()+[integer("TimeSignatureDisplayFlags",9)])))
        let extra = field("Additional Attributes",2,u16(6)+fields([integer("PLAS",1920)]))
        rejects(envelope(second:signature(defaults()+[extra])))
    }

    @Test func allTenPinnedFactorySignaturesRecoverWithoutExecutingTheSource() throws {
        let workspace = URL(fileURLWithPath:#filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let manifestURL = workspace.appendingPathComponent("research/evidence/cpr-static/cpr-signature-001/fixtures/finding-v1.json")
        let manifest = try #require(JSONSerialization.jsonObject(with:Data(contentsOf:manifestURL)) as? [String:Any])
        let records = try #require(manifest["records"] as? [[String:Any]])
        #expect(records.count == 10)
        for record in records {
            let path = try #require(record["source"] as? String)
            let expectedSHA = try #require(record["source_sha256"] as? String)
            let object = try #require(record["signature_object"] as? [String:Any])
            let offset = try #require(object["offset"] as? Int)
            let source = workspace.appendingPathComponent(path)
            let before = try Data(contentsOf:source)
            #expect(cprSHA256(before) == expectedSHA)
            let recovered = try recover(before)
            let signature = try #require(recovered.signature, "No supported signature in \(source.lastPathComponent): \(recovered.unsupported)")
            #expect(signature.beat == 0 && signature.numerator == 4 && signature.denominator == 4)
            #expect(recovered.objects.contains { $0.className == "MSignatureTrackEvent" && $0.objectOffset == offset })
            #expect(try Data(contentsOf:source) == before)
        }
    }
}

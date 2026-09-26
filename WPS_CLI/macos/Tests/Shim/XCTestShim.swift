// 仅在无 XCTest 的工具链（Command Line Tools）下编译：最小 XCTest 兼容层，
// 使同一份测试既可用 `swift test`（Xcode）运行，也可由 build.sh 编译为可执行文件运行。
import Foundation

class XCTestCase { required init() {} }

var shimFailures = 0
var shimCount = 0

func shimFail(_ msg: String, _ file: StaticString, _ line: UInt) {
    shimFailures += 1
    print("    ✗ \(file):\(line): \(msg)")
}

func XCTAssertEqual<T: Equatable>(_ a: @autoclosure () throws -> T, _ b: @autoclosure () throws -> T,
                                  _ msg: String = "", file: StaticString = #file, line: UInt = #line) {
    do { let x = try a(), y = try b(); if x != y { shimFail("\(x) != \(y) \(msg)", file, line) } }
    catch { shimFail("threw \(error)", file, line) }
}
func XCTAssertEqual(_ a: Double, _ b: Double, accuracy: Double,
                    file: StaticString = #file, line: UInt = #line) {
    if abs(a - b) > accuracy { shimFail("\(a) != \(b)", file, line) }
}
func XCTAssertTrue(_ c: @autoclosure () throws -> Bool, _ msg: String = "",
                   file: StaticString = #file, line: UInt = #line) {
    if (try? c()) != true { shimFail("not true \(msg)", file, line) }
}
func XCTAssertFalse(_ c: @autoclosure () throws -> Bool, _ msg: String = "",
                    file: StaticString = #file, line: UInt = #line) {
    if (try? c()) != false { shimFail("not false \(msg)", file, line) }
}

func run<T: XCTestCase>(_ type: T.Type, _ tests: [(String, (T) throws -> Void)]) {
    for (name, body) in tests {
        shimCount += 1
        let before = shimFailures
        do { try body(type.init()) } catch { shimFail("threw \(error)", #file, #line) }
        print("\(shimFailures == before ? "✓" : "✗") \(type).\(name)")
    }
}

func finishShim() {
    print("\nRan \(shimCount) tests, \(shimFailures) failures")
    exit(shimFailures == 0 ? 0 : 1)
}

#if canImport(XCTest)
import XCTest
#endif
#if canImport(WPSBackupCore)
@testable import WPSBackupCore
#endif
import Foundation

final class LaunchAgentTests: XCTestCase {
    static let allTests: [(String, (LaunchAgentTests) throws -> Void)] = [
        ("testSchedulerPlist", { try $0.testSchedulerPlist() }),
        ("testLoginPlist", { try $0.testLoginPlist() }),
        ("testParseHealthyJob", { $0.testParseHealthyJob() }),
        ("testParseSpawnFailedCodesigning", { $0.testParseSpawnFailedCodesigning() }),
        ("testParseNotLoaded", { $0.testParseNotLoaded() }),
        ("testParseDisabled", { $0.testParseDisabled() }),
        ("testSpawnFailedIsError", { $0.testSpawnFailedIsError() }),
    ]

    func decode(_ d: Data) throws -> [String: Any] {
        try PropertyListSerialization.propertyList(from: d, format: nil) as! [String: Any]
    }

    func testSchedulerPlist() throws {
        let p = try decode(LaunchAgentPlist.scheduler(runnerPath: "/A/WPS Backup.app/Contents/MacOS/wps-backup-runner"))
        XCTAssertEqual(p["Label"] as? String, AppConstants.schedulerLabel)
        XCTAssertEqual(p["ProgramArguments"] as? [String],
                       ["/A/WPS Backup.app/Contents/MacOS/wps-backup-runner", "scheduled"])
        XCTAssertEqual((p["StartCalendarInterval"] as? [String: Int])?["Minute"], 0)
        XCTAssertEqual(p["RunAtLoad"] as? Bool, false)
        XCTAssertTrue(p["BundleProgram"] == nil, "不使用 SMAppService 的 BundleProgram（会产生 cdhash 约束）")
    }

    func testLoginPlist() throws {
        let p = try decode(LaunchAgentPlist.loginItem(appPath: "/A/WPS Backup.app"))
        XCTAssertEqual(p["Label"] as? String, AppConstants.loginLabel)
        XCTAssertEqual(p["ProgramArguments"] as? [String], ["/usr/bin/open", "-a", "/A/WPS Backup.app"])
        XCTAssertEqual(p["RunAtLoad"] as? Bool, true)
    }

    // 2026-09-26 实测：SMAppService 注册的 agent 被 launchd 以代码签名拒绝
    let spawnFailed = """
    gui/501/cc.all4world.wpsbackup.agent = {
    \tstate = not running
    \truns = 1
    \tlast exit reason = OS_REASON_CODESIGNING
    \tjob state = spawn failed
    }
    """

    func testParseHealthyJob() {
        let out = "gui/501/x = {\n\tstate = not running\n\tlast exit code = 0\n}"
        XCTAssertEqual(parseAgentState(printOutput: out, disabled: false), .enabled)
    }

    func testParseSpawnFailedCodesigning() {
        XCTAssertEqual(parseAgentState(printOutput: spawnFailed, disabled: false), .spawnFailed)
    }

    func testParseNotLoaded() {
        XCTAssertEqual(parseAgentState(printOutput: nil, disabled: false), .notRegistered)
    }

    func testParseDisabled() {
        XCTAssertEqual(parseAgentState(printOutput: nil, disabled: true), .requiresApproval)
        let pd = "disabled services = {\n\t\"cc.all4world.wpsbackup.scheduler\" => disabled\n\t\"x\" => enabled\n}"
        XCTAssertTrue(isDisabled(label: AppConstants.schedulerLabel, printDisabledOutput: pd))
        XCTAssertFalse(isDisabled(label: "x", printDisabledOutput: pd))
    }

    func testSpawnFailedIsError() {
        let st = EngineStatus(running: false, progress: nil, lastRun: nil, lastSuccessAt: nil, heartbeat: nil,
                              scheduleHour: 20, nextRunAt: nil, cli: nil, auth: nil,
                              health: Health(level: .ok, reasons: []), snapshot: nil, backupDir: nil, logFile: nil)
        XCTAssertEqual(mergeHealth(engine: st, agent: .spawnFailed).level, .error)
    }
}

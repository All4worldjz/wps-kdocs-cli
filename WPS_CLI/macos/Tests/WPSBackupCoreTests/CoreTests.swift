#if canImport(XCTest)
import XCTest
#endif
#if canImport(WPSBackupCore)
@testable import WPSBackupCore
#endif
import Foundation

final class SettingsTests: XCTestCase {
    static let allTests: [(String, (SettingsTests) throws -> Void)] = [("testDefaultsAndRoundTrip", { try $0.testDefaultsAndRoundTrip() }), ("testCorruptFileFallsBackToDefaults", { try $0.testCorruptFileFallsBackToDefaults() })]
    func testDefaultsAndRoundTrip() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let url = dir.appendingPathComponent("settings.json")
        var s = AppSettings.load(from: url, defaultEngineRoot: "/eng")
        XCTAssertEqual(s.engineRoot, "/eng")
        XCTAssertEqual(s.scheduleHour, 20)
        XCTAssertFalse(s.cacheScan, "缓存扫描默认关闭（需完全磁盘访问权限）")
        s.scheduleHour = 7
        try s.save(to: url)
        XCTAssertEqual(AppSettings.load(from: url, defaultEngineRoot: "/other").scheduleHour, 7)
    }

    func testCorruptFileFallsBackToDefaults() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("settings.json")
        try "{".write(to: url, atomically: true, encoding: .utf8)
        XCTAssertEqual(AppSettings.load(from: url, defaultEngineRoot: "/eng").engineRoot, "/eng")
    }
}

final class EngineEnvironmentTests: XCTestCase {
    static let allTests: [(String, (EngineEnvironmentTests) throws -> Void)] = [("testEnvironmentAndArguments", { $0.testEnvironmentAndArguments() })]
    func testEnvironmentAndArguments() {
        var s = AppSettings.defaults(engineRoot: "/eng")
        s.scheduleHour = 6; s.workers = 2; s.exportDocx = false; s.cacheScan = false
        let env = EngineEnvironment(settings: s, home: "/Users/u")
        XCTAssertTrue(env.variables["PATH"]!.hasPrefix("/Users/u/.local/bin:"))
        XCTAssertFalse(env.variables["PATH"]!.contains("/usr/local/bin"), "避开旧版 v0.1.0")
        XCTAssertEqual(env.variables["WPS_BACKUP_HOUR"], "6")
        XCTAssertEqual(env.variables["WPS_BACKUP_WORKERS"], "2")
        XCTAssertEqual(env.variables["WPS_AIRPAGE_EXPORT_DOCX"], "0")
        XCTAssertEqual(env.variables["WPS_OTL_CACHE_SCAN"], "0")
        XCTAssertEqual(env.arguments(["scheduled"]), [s.pythonPath, "/eng/wps_backup.py", "scheduled"])
        XCTAssertEqual(env.stateDir, "/eng/wps_backup_state")
    }
}

final class StatusDecodingTests: XCTestCase {
    static let allTests: [(String, (StatusDecodingTests) throws -> Void)] = [("testDecodesEngineStatusJSON", { try $0.testDecodesEngineStatusJSON() }), ("testDecodesProgress", { try $0.testDecodesProgress() })]
    func testDecodesEngineStatusJSON() throws {
        let json = """
        {"running": false, "progress": null,
         "last_run": {"trigger": "schedule", "started_at": "2026-09-26T20:00:00", "finished_at": "2026-09-26T20:03:00",
                      "exit_code": 0, "counts": {"new": 2, "failed": 0}, "error_count": 0, "errors": []},
         "last_success_at": "2026-09-26T20:03:00", "heartbeat": {"at": "2026-09-26T21:00:00"},
         "schedule_hour": 20, "next_run_at": "2026-09-27T20:00:00",
         "cli": {"path": "/x", "found": true, "version": "0.3.6"},
         "auth": {"status": "valid", "refreshable": true, "refresh_token_expires_at": "2027-09-26T12:00:00+08:00", "airpage_scope": true},
         "health": {"level": "ok", "reasons": []},
         "snapshot": {"snapshot_count": 1038, "total_size": 26819390616, "last_backup_at": "2026-09-26 11:01:19"},
         "backup_dir": "/b", "log_file": "/l", "extra_field": 1}
        """
        let st = try EngineStatus.decode(Data(json.utf8))
        XCTAssertEqual(st.health.level, .ok)
        XCTAssertEqual(st.lastRun?.exitCode, 0)
        XCTAssertEqual(st.lastRun?.counts["new"], 2)
        XCTAssertEqual(st.snapshot?.snapshotCount, 1038)
        XCTAssertEqual(st.heartbeat?.at, "2026-09-26T21:00:00")
    }

    func testDecodesProgress() throws {
        let p = try JSONDecoder().decode(RunProgress.self, from: Data(
            #"{"running": true, "pid": 42, "trigger": "manual", "started_at": "x", "phase": "download", "done": 3, "total": 10, "current": "a.docx"}"#.utf8))
        XCTAssertEqual(p.fraction, 0.3, accuracy: 0.001)
    }
}

final class HealthMergeTests: XCTestCase {
    static let allTests: [(String, (HealthMergeTests) throws -> Void)] = [("testAgentRequiresApprovalIsError", { $0.testAgentRequiresApprovalIsError() }), ("testAgentNotRegisteredIsError", { $0.testAgentNotRegisteredIsError() }), ("testStaleHeartbeatIsWarn", { $0.testStaleHeartbeatIsWarn() }), ("testEngineUnavailableIsError", { $0.testEngineUnavailableIsError() }), ("testAllGood", { $0.testAllGood() }), ("testEngineWarnKept", { $0.testEngineWarnKept() })]
    let now = ISO8601Local.parse("2026-09-26T21:30:00")!

    func engine(_ level: HealthLevel, heartbeat: String? = "2026-09-26T21:00:00") -> EngineStatus {
        EngineStatus(running: false, progress: nil, lastRun: nil, lastSuccessAt: nil,
                     heartbeat: heartbeat.map { Heartbeat(at: $0) }, scheduleHour: 20, nextRunAt: nil,
                     cli: nil, auth: nil, health: Health(level: level, reasons: level == .ok ? [] : ["x"]),
                     snapshot: nil, backupDir: nil, logFile: nil)
    }

    func testAgentRequiresApprovalIsError() {
        let h = mergeHealth(engine: engine(.ok), agent: .requiresApproval, now: now)
        XCTAssertEqual(h.level, .error)
        XCTAssertTrue(h.reasons.first!.contains("登录项"))
    }

    func testAgentNotRegisteredIsError() {
        XCTAssertEqual(mergeHealth(engine: engine(.ok), agent: .notRegistered, now: now).level, .error)
    }

    func testStaleHeartbeatIsWarn() {
        let h = mergeHealth(engine: engine(.ok, heartbeat: "2026-09-26T17:00:00"), agent: .enabled, now: now)
        XCTAssertEqual(h.level, .warn)
    }

    func testEngineUnavailableIsError() {
        XCTAssertEqual(mergeHealth(engine: nil, agent: .enabled, now: now, engineError: "boom").level, .error)
    }

    func testAllGood() {
        XCTAssertEqual(mergeHealth(engine: engine(.ok), agent: .enabled, now: now).level, .ok)
    }

    func testEngineWarnKept() {
        XCTAssertEqual(mergeHealth(engine: engine(.warn), agent: .enabled, now: now).level, .warn)
    }
}

#if !canImport(XCTest)
@main struct ShimMain {
    static func main() {
        run(SettingsTests.self, SettingsTests.allTests)
        run(EngineEnvironmentTests.self, EngineEnvironmentTests.allTests)
        run(StatusDecodingTests.self, StatusDecodingTests.allTests)
        run(HealthMergeTests.self, HealthMergeTests.allTests)
        run(LaunchAgentTests.self, LaunchAgentTests.allTests)
        finishShim()
    }
}
#endif

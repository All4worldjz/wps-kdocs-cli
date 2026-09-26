// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "WPSBackup",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "WPSBackupCore"),
        .executableTarget(name: "WPSBackup", dependencies: ["WPSBackupCore"]),
        .executableTarget(name: "wps-backup-runner", dependencies: ["WPSBackupCore"]),
        .testTarget(name: "WPSBackupCoreTests", dependencies: ["WPSBackupCore"]),
    ]
)

import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
  private let screenSecurityChannelName = "com.yonsei.dating/screen_security"
  private weak var privacyOverlayView: UIView?
  private var screenSecurityEnabled = false
  private var screenshotOverlayHideWorkItem: DispatchWorkItem?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    if let controller = window?.rootViewController as? FlutterViewController {
      let channel = FlutterMethodChannel(
        name: screenSecurityChannelName,
        binaryMessenger: controller.binaryMessenger
      )
      channel.setMethodCallHandler { [weak self] call, result in
        switch call.method {
        case "enableProtection":
          self?.enableScreenSecurityProtection()
          result(nil)
        case "enableSensitiveProtection":
          result(nil)
        case "disableSensitiveProtection":
          result(nil)
        default:
          result(FlutterMethodNotImplemented)
        }
      }
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  override func applicationWillResignActive(_ application: UIApplication) {
    super.applicationWillResignActive(application)
    if screenSecurityEnabled {
      showPrivacyOverlay()
    }
  }

  override func applicationDidBecomeActive(_ application: UIApplication) {
    super.applicationDidBecomeActive(application)
    guard screenSecurityEnabled else { return }
    updatePrivacyOverlayVisibility()
  }

  private func enableScreenSecurityProtection() {
    guard !screenSecurityEnabled else {
      updatePrivacyOverlayVisibility()
      return
    }

    screenSecurityEnabled = true

    NotificationCenter.default.addObserver(
      self,
      selector: #selector(handleScreenCaptureChanged),
      name: UIScreen.capturedDidChangeNotification,
      object: nil
    )

    NotificationCenter.default.addObserver(
      self,
      selector: #selector(handleUserDidTakeScreenshot),
      name: UIApplication.userDidTakeScreenshotNotification,
      object: nil
    )

    updatePrivacyOverlayVisibility()
  }

  @objc private func handleScreenCaptureChanged() {
    updatePrivacyOverlayVisibility()
  }

  @objc private func handleUserDidTakeScreenshot() {
    // iOS does not allow apps to block screenshots entirely.
    // Keep the splash overlay visible a bit longer to maximize the chance
    // that the captured frame contains the privacy cover instead of app content.
    showPrivacyOverlay()

    screenshotOverlayHideWorkItem?.cancel()
    let workItem = DispatchWorkItem { [weak self] in
      self?.updatePrivacyOverlayVisibility()
    }
    screenshotOverlayHideWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0, execute: workItem)
  }

  private func updatePrivacyOverlayVisibility() {
    guard screenSecurityEnabled else { return }

    let isCaptured = UIScreen.main.isCaptured
    let isInactive = UIApplication.shared.applicationState != .active
    if isCaptured || isInactive {
      showPrivacyOverlay()
    } else {
      hidePrivacyOverlay()
    }
  }

  private func showPrivacyOverlay() {
    guard let window = window else { return }

    if let overlay = privacyOverlayView {
      overlay.isHidden = false
      window.bringSubviewToFront(overlay)
      return
    }

    let overlay = UIView(frame: window.bounds)
    overlay.backgroundColor = UIColor(red: 0.98, green: 0.98, blue: 0.98, alpha: 1.0)
    overlay.isUserInteractionEnabled = false
    overlay.autoresizingMask = [.flexibleWidth, .flexibleHeight]

    let titleLabel = UILabel()
    titleLabel.translatesAutoresizingMaskIntoConstraints = false
    titleLabel.text = "설레연"
    titleLabel.font = UIFont.systemFont(ofSize: 36, weight: .bold)
    titleLabel.textColor = UIColor(red: 1.0, green: 0.42, blue: 0.54, alpha: 1.0)

    let spinner = UIActivityIndicatorView(style: .medium)
    spinner.translatesAutoresizingMaskIntoConstraints = false
    spinner.color = UIColor(red: 1.0, green: 0.42, blue: 0.54, alpha: 1.0)
    spinner.startAnimating()

    overlay.addSubview(titleLabel)
    overlay.addSubview(spinner)

    NSLayoutConstraint.activate([
      titleLabel.centerXAnchor.constraint(equalTo: overlay.centerXAnchor),
      titleLabel.centerYAnchor.constraint(equalTo: overlay.centerYAnchor, constant: -10),
      spinner.centerXAnchor.constraint(equalTo: overlay.centerXAnchor),
      spinner.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 14)
    ])

    window.addSubview(overlay)
    window.bringSubviewToFront(overlay)
    privacyOverlayView = overlay
  }

  private func hidePrivacyOverlay() {
    screenshotOverlayHideWorkItem?.cancel()
    screenshotOverlayHideWorkItem = nil
    privacyOverlayView?.isHidden = true
  }
}

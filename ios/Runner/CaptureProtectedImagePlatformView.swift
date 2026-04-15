import CoreImage
import Flutter
import UIKit

final class CaptureProtectedImageViewFactory: NSObject, FlutterPlatformViewFactory {
  func createArgsCodec() -> FlutterMessageCodec & NSObjectProtocol {
    FlutterStandardMessageCodec.sharedInstance()
  }

  func create(
    withFrame frame: CGRect,
    viewIdentifier viewId: Int64,
    arguments args: Any?
  ) -> FlutterPlatformView {
    CaptureProtectedImagePlatformView(
      frame: frame,
      viewId: viewId,
      arguments: args as? [String: Any] ?? [:]
    )
  }
}

final class CaptureProtectedImagePlatformView: NSObject, FlutterPlatformView {
  private let secureImageView: SecureCaptureImageView

  init(frame: CGRect, viewId: Int64, arguments: [String: Any]) {
    secureImageView = SecureCaptureImageView(frame: frame, arguments: arguments)
    super.init()
  }

  func view() -> UIView {
    secureImageView
  }
}

private enum CaptureProtectedImageFit: String {
  case cover
  case contain

  var contentMode: UIView.ContentMode {
    switch self {
    case .cover:
      return .scaleAspectFill
    case .contain:
      return .scaleAspectFit
    }
  }
}

private final class SecureCaptureImageView: UIView {
  private static let imageCache = NSCache<NSString, UIImage>()
  private static let ciContext = CIContext(options: nil)

  private let secureTextField = UITextField()
  private let contentView = UIView()
  private let imageView = UIImageView()
  private let placeholderView = UIImageView(image: UIImage(systemName: "person.fill"))

  private let imageUrl: String
  private let fit: CaptureProtectedImageFit
  private let borderRadius: CGFloat
  private let isCircular: Bool
  private let blurEnabled: Bool
  private let blurSigma: CGFloat
  private let grayscale: Bool
  private let backgroundUIColor: UIColor
  private let placeholderIconUIColor: UIColor
  private let placeholderIconSize: CGFloat

  private var currentTask: URLSessionDataTask?
  private var currentImageUrl: String?
  private var contentViewConstraints: [NSLayoutConstraint] = []

  init(frame: CGRect, arguments: [String: Any]) {
    imageUrl = arguments["imageUrl"] as? String ?? ""
    fit = CaptureProtectedImageFit(
      rawValue: (arguments["fit"] as? String ?? "cover").lowercased()
    ) ?? .cover
    borderRadius = CGFloat.number(from: arguments["borderRadius"])
    isCircular = arguments["isCircular"] as? Bool ?? false
    blurEnabled = arguments["blurEnabled"] as? Bool ?? false
    blurSigma = CGFloat.number(from: arguments["blurSigma"], fallback: 7)
    grayscale = arguments["grayscale"] as? Bool ?? false
    backgroundUIColor = UIColor(argbValue: arguments["backgroundColor"])
    placeholderIconUIColor = UIColor(
      argbValue: arguments["placeholderIconColor"],
      fallback: UIColor.systemGray2
    )
    placeholderIconSize = CGFloat.number(from: arguments["placeholderIconSize"], fallback: 28)

    super.init(frame: frame)
    configureViewHierarchy()
    loadImageIfNeeded()
  }

  @available(*, unavailable)
  required init?(coder: NSCoder) {
    nil
  }

  deinit {
    currentTask?.cancel()
  }

  override func didMoveToWindow() {
    super.didMoveToWindow()
    guard window != nil else { return }
    DispatchQueue.main.async { [weak self] in
      self?.attachContentToSecureContainerIfNeeded()
    }
  }

  override func layoutSubviews() {
    super.layoutSubviews()
    updateCornerRadius()
  }

  private func configureViewHierarchy() {
    backgroundColor = .clear
    isOpaque = false
    clipsToBounds = true

    secureTextField.translatesAutoresizingMaskIntoConstraints = false
    secureTextField.isSecureTextEntry = true
    secureTextField.isUserInteractionEnabled = false
    secureTextField.isEnabled = false
    secureTextField.backgroundColor = .clear
    secureTextField.textColor = .clear
    secureTextField.tintColor = .clear
    secureTextField.borderStyle = .none
    addSubview(secureTextField)

    contentView.translatesAutoresizingMaskIntoConstraints = false
    contentView.backgroundColor = backgroundUIColor
    contentView.clipsToBounds = true

    imageView.translatesAutoresizingMaskIntoConstraints = false
    imageView.contentMode = fit.contentMode
    imageView.clipsToBounds = true
    imageView.backgroundColor = backgroundUIColor
    contentView.addSubview(imageView)

    placeholderView.translatesAutoresizingMaskIntoConstraints = false
    placeholderView.contentMode = .scaleAspectFit
    placeholderView.tintColor = placeholderIconUIColor
    contentView.addSubview(placeholderView)

    NSLayoutConstraint.activate([
      secureTextField.leadingAnchor.constraint(equalTo: leadingAnchor),
      secureTextField.trailingAnchor.constraint(equalTo: trailingAnchor),
      secureTextField.topAnchor.constraint(equalTo: topAnchor),
      secureTextField.bottomAnchor.constraint(equalTo: bottomAnchor),

      imageView.leadingAnchor.constraint(equalTo: contentView.leadingAnchor),
      imageView.trailingAnchor.constraint(equalTo: contentView.trailingAnchor),
      imageView.topAnchor.constraint(equalTo: contentView.topAnchor),
      imageView.bottomAnchor.constraint(equalTo: contentView.bottomAnchor),

      placeholderView.centerXAnchor.constraint(equalTo: contentView.centerXAnchor),
      placeholderView.centerYAnchor.constraint(equalTo: contentView.centerYAnchor),
      placeholderView.widthAnchor.constraint(equalToConstant: placeholderIconSize),
      placeholderView.heightAnchor.constraint(equalToConstant: placeholderIconSize),
    ])

    attachContent(to: self)
    updateCornerRadius()
    showPlaceholder()
  }

  private func updateCornerRadius() {
    let radius = isCircular ? min(bounds.width, bounds.height) / 2 : borderRadius
    layer.cornerRadius = radius
    imageView.layer.cornerRadius = radius
  }

  private func attachContentToSecureContainerIfNeeded() {
    let secureContainer = resolveSecureContainerView() ?? self
    guard contentView.superview !== secureContainer else { return }
    attachContent(to: secureContainer)
  }

  private func resolveSecureContainerView() -> UIView? {
    secureTextField.layoutIfNeeded()

    if let canvasView = findCanvasView(in: secureTextField) {
      return canvasView
    }
    return secureTextField.subviews.first
  }

  private func findCanvasView(in view: UIView) -> UIView? {
    for subview in view.subviews {
      let className = NSStringFromClass(type(of: subview))
      if className.contains("CanvasView") {
        return subview
      }
      if let nested = findCanvasView(in: subview) {
        return nested
      }
    }
    return nil
  }

  private func attachContent(to hostView: UIView) {
    NSLayoutConstraint.deactivate(contentViewConstraints)
    contentViewConstraints.removeAll()
    contentView.removeFromSuperview()

    hostView.addSubview(contentView)
    contentViewConstraints = [
      contentView.leadingAnchor.constraint(equalTo: hostView.leadingAnchor),
      contentView.trailingAnchor.constraint(equalTo: hostView.trailingAnchor),
      contentView.topAnchor.constraint(equalTo: hostView.topAnchor),
      contentView.bottomAnchor.constraint(equalTo: hostView.bottomAnchor),
    ]
    NSLayoutConstraint.activate(contentViewConstraints)
    hostView.setNeedsLayout()
    hostView.layoutIfNeeded()
  }

  private func loadImageIfNeeded() {
    currentTask?.cancel()
    currentImageUrl = imageUrl

    guard !imageUrl.isEmpty, let url = URL(string: imageUrl) else {
      showPlaceholder()
      return
    }

    if let cachedImage = Self.imageCache.object(forKey: imageUrl as NSString) {
      applyResolvedImage(cachedImage, for: imageUrl)
      return
    }

    let request = URLRequest(
      url: url,
      cachePolicy: .returnCacheDataElseLoad,
      timeoutInterval: 30
    )

    currentTask = URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
      guard let self else { return }
      guard self.currentImageUrl == self.imageUrl else { return }
      guard let data, let image = UIImage(data: data) else {
        DispatchQueue.main.async { [weak self] in
          self?.showPlaceholder()
        }
        return
      }

      Self.imageCache.setObject(image, forKey: self.imageUrl as NSString)
      self.applyResolvedImage(image, for: self.imageUrl)
    }
    currentTask?.resume()
  }

  private func applyResolvedImage(_ image: UIImage, for urlString: String) {
    let processedImage = processImage(image)
    DispatchQueue.main.async { [weak self] in
      guard let self else { return }
      guard self.currentImageUrl == urlString else { return }
      self.imageView.image = processedImage
      self.placeholderView.isHidden = true
    }
  }

  private func showPlaceholder() {
    imageView.image = nil
    placeholderView.isHidden = false
  }

  private func processImage(_ image: UIImage) -> UIImage {
    guard blurEnabled || grayscale else { return image }
    guard var ciImage = CIImage(image: image) else { return image }

    if grayscale {
      let grayscaleFilter = CIFilter(name: "CIColorControls")
      grayscaleFilter?.setValue(ciImage, forKey: kCIInputImageKey)
      grayscaleFilter?.setValue(0, forKey: kCIInputSaturationKey)
      if let output = grayscaleFilter?.outputImage {
        ciImage = output
      }
    }

    if blurEnabled {
      let blurFilter = CIFilter(name: "CIGaussianBlur")
      blurFilter?.setValue(ciImage, forKey: kCIInputImageKey)
      blurFilter?.setValue(max(0, blurSigma), forKey: kCIInputRadiusKey)
      if let output = blurFilter?.outputImage {
        ciImage = output.cropped(to: ciImage.extent)
      }
    }

    guard let cgImage = Self.ciContext.createCGImage(ciImage, from: ciImage.extent) else {
      return image
    }
    return UIImage(cgImage: cgImage, scale: image.scale, orientation: image.imageOrientation)
  }
}

private extension UIColor {
  convenience init(argbValue: Any?, fallback: UIColor = UIColor.systemGray6) {
    guard let argb = UInt32.number(from: argbValue) else {
      let resolved = fallback.rgbaComponents
      self.init(
        red: resolved.red,
        green: resolved.green,
        blue: resolved.blue,
        alpha: resolved.alpha
      )
      return
    }

    let alpha = CGFloat((argb >> 24) & 0xFF) / 255.0
    let red = CGFloat((argb >> 16) & 0xFF) / 255.0
    let green = CGFloat((argb >> 8) & 0xFF) / 255.0
    let blue = CGFloat(argb & 0xFF) / 255.0
    self.init(red: red, green: green, blue: blue, alpha: alpha)
  }
}

private extension CGFloat {
  static func number(from value: Any?, fallback: CGFloat = 0) -> CGFloat {
    if let value = value as? CGFloat {
      return value
    }
    if let number = value as? NSNumber {
      return CGFloat(number.doubleValue)
    }
    if let string = value as? String, let doubleValue = Double(string) {
      return CGFloat(doubleValue)
    }
    return fallback
  }
}

private extension UInt32 {
  static func number(from value: Any?) -> UInt32? {
    if let value = value as? UInt32 {
      return value
    }
    if let number = value as? NSNumber {
      return number.uint32Value
    }
    if let string = value as? String, let intValue = UInt32(string) {
      return intValue
    }
    return nil
  }
}

private extension UIColor {
  var rgbaComponents: (red: CGFloat, green: CGFloat, blue: CGFloat, alpha: CGFloat) {
    var red: CGFloat = 0
    var green: CGFloat = 0
    var blue: CGFloat = 0
    var alpha: CGFloat = 0
    if getRed(&red, green: &green, blue: &blue, alpha: &alpha) {
      return (red, green, blue, alpha)
    }
    return (0.95, 0.95, 0.95, 1.0)
  }
}

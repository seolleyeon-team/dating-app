# App Review safety checklist

- [x] Report-and-block records retain the reporter, reported user, source and content reference.
- [x] Bamboo Forest posts and comments are submitted through server-side validation.
- [x] Community report/block controls are available for content written by another user.
- [x] A reported/blocked author is filtered from the reporter's Bamboo Forest view.
- [x] Direct-chat text messages are validated and denied after a mutual safety block.
- [x] Production screen-capture protection remains enabled; an explicit internal QA build flag can disable it.
- [x] IAP price labels use the store-provided localized price.
- [x] App and web support contact use support@seolleyeon.com.

## Release verification (manual)

- [ ] Deploy Cloud Functions and Firestore Rules together.
- [ ] Test reporting/blocking with two production accounts and confirm new direct messages are denied.
- [ ] Test a post and a comment report, then verify the report record is visible to operations only.
- [ ] Test the QA capture build on a physical iPhone; confirm the normal release build still masks capture.
- [ ] Test every IAP product from TestFlight/Sandbox and confirm the displayed price is returned by StoreKit.

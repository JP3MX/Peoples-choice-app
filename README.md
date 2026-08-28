# Squawk King IA — People's Choice Android Release

Android package: `com.jp3aviation.peopleschoice`

This package is intentionally different from the separate Squawk King IA package `com.jp3aviation.squawkking`. Google Play package names cannot be changed or reused after publication.

## Required private configuration

### Production backend

Set `REACT_APP_BACKEND_URL` to the deployed HTTPS backend before running `npm run build`. The frontend now fails immediately if this value is missing or is not HTTPS.

Also add the same URL as the GitHub repository variable named `REACT_APP_BACKEND_URL`.

### Release signing

Never commit the keystore, passwords, or `frontend/android/keystore.properties`.

Create `frontend/android/keystore.properties` locally:

```properties
storeFile=../YOUR_RELEASE_KEY.keystore
storePassword=YOUR_STORE_PASSWORD
keyAlias=YOUR_KEY_ALIAS
keyPassword=YOUR_KEY_PASSWORD
```

The path is resolved from `frontend/android/app`. A keystore saved directly in `frontend/android` therefore uses `../filename.keystore`.

Back up the original upload keystore and passwords in at least two secure locations. Losing the upload key can block future releases unless Play App Signing key-reset procedures are available.

## Verified release build

From `frontend`:

```bash
npm ci
npm run build
npx cap sync android
cd android
./gradlew clean testReleaseUnitTest bundleRelease
jarsigner -verify -verbose -certs app/build/outputs/bundle/release/app-release.aab
```

On Windows, use `gradlew.bat`.

Upload only:

`frontend/android/app/build/outputs/bundle/release/app-release.aab`

Do not upload the CI artifact to production. CI uses a disposable signing key and may use a non-routable backend URL when the repository variable is absent.

For every subsequent Play release, increase `versionCode` in `frontend/android/app/build.gradle`. Never reuse a previously uploaded version code.

## Play Console completion

Before production submission:

- Enroll in Play App Signing and upload the AAB signed with the permanent upload key.
- Confirm the Play listing uses package `com.jp3aviation.peopleschoice`.
- Supply a real app icon, feature graphic, phone screenshots, short description, and full description.
- Publish the privacy policy at the production web route `/privacy`.
- Supply the external deletion URL `/account-deletion`.
- Complete Data Safety based on account, aircraft, chat, logbook, uploaded-file, billing, email, AI-provider, and diagnostic-log handling.
- Put reviewer credentials only in Play Console App access instructions. Rotate the old reviewer password because it previously existed in repository history.
- Complete Content rating, Ads declaration, Target audience, News/Health/Financial declarations as applicable.
- Verify live registration, login, password reset, account deletion, manual/media download, AI-response reporting, and subscription entitlement on a physical Android device.
- If the Play developer account is a personal account created after November 13, 2023, complete a closed test with at least 12 continuously opted-in testers for 14 days before applying for production access.
- Confirm Resend uses a production API key and verified sender domain.
- Confirm Stripe is live for the website. Direct Stripe purchase UI is disabled in the Android app to avoid an unapproved in-app alternative billing flow.

## Security controls included

- Markdown HTML is sanitized with DOMPurify.
- Protected downloads require an Authorization header; tokens are no longer placed in URLs.
- Cleartext Android traffic and Android backups are disabled.
- FileProvider is restricted to app-owned files and cache.
- Account deletion cancels the Stripe customer first, removes stored uploads, and deletes user-owned database records.
- Release tasks fail when signing configuration is absent or invalid.
- Reviewer credentials are no longer displayed or stored in current source files.

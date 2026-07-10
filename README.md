# Connect Extensions (staging)

A staging environment for developing Connect extensions before they're published
to the [connect-extensions](https://github.com/posit-dev/connect-extensions)
gallery.

## How this repo works

You develop and perfect **one** extension at a time here, deploy it to confirm it
works, and once it's ready it moves to `connect-extensions` for official
publication and release.

Because of that, only the extension you're actively working on should be under CI
and in the gallery feed at a time, not all in-development extensions together.
When you start on one, register it in the integration-test paths-filter (with a
real `minimumConnectVersion`); when it graduates, remove it from here. This is
deliberately different from `connect-extensions`, which tests every published
extension on every change to guard against regressions across the live gallery.

### Adding Content

See the [contributing guide](CONTRIBUTING.md)
to learn how to contribute content, and add it to the Connect Gallery.

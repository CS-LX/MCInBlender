# CI and release policy

The default branch is `main`. GitHub repository settings allow **squash merge only**:
one merged PR produces one main-branch commit. Feature branch pushes and PR updates
do not run CI. Build checks run after the squash commit reaches main.

`.github/workflows/packages.yml` responds only to pushes to `main` and version-tag
pushes. Tag builds first validate an exact `vX.X.X.X` name, equality with `VERSION`,
and that the commit is reachable from `origin/main`. Tags on unmerged feature
commits cannot publish. There is no `pull_request`, scheduled or manual workflow.

| Event | GitHub release | Filename example |
| --- | --- | --- |
| Ordinary main commit | Prerelease `ci-v0.1.0.0+g01234567` | `MCInBlender-ci-v0.1.0.0+g01234567-windows-x64-addon.zip` |
| Tag `v0.1.0.0` on main history | Stable release `v0.1.0.0` | `MCInBlender-release-v0.1.0.0-windows-x64-addon.zip` |

Each build also publishes `-bundle.zip`, `-minecraft.mrpack`, `SHA256SUMS.txt`,
and `build-info.json`. Full SHA and protocol/dependency versions are recorded in
the add-on and Minecraft pack. Minecraft/Fabric metadata uses a three-part SemVer
plus revision metadata (`0.1.0+rev.0`); the user-facing version/tag retains all four
components. A CI build adds the short SHA as build metadata.

To release:

1. Change `VERSION` to the intended four-part version in a PR.
2. Merge with squash into main and wait for its CI package to pass.
3. Tag that validated commit: `git tag vX.X.X.X COMMIT_SHA`, then `git push origin vX.X.X.X`.
4. The tag workflow rebuilds and publishes the stable packages. The earlier CI
   prerelease remains identifiable; it is not silently renamed or promoted.

Both channels run Java compilation/tests, focused Python tests, package version/
payload/hash checks, load the bundled x64 DLL, and install/enable the ZIP in Blender
with an isolated profile. Real GPU gameplay is checked locally for release changes
that affect it; hosted CI does not claim to exercise interactive gameplay.

CI downloads Blender 5.0.1 from Blender's official server and verifies its published
SHA-256 before installation. It does not redistribute Blender or Minecraft.
The bundle contains the MIT-licensed bridge/add-on and Apache-2.0 Fabric API,
with license notices preserved in the dependency JARs and package notices.

## Build the same package locally

Windows x64, Python with NumPy, JDK 25 and GCC or MSVC are needed only by maintainers:

```powershell
python scripts/release_metadata.py
$version = (Get-Content dist/build-info.json | ConvertFrom-Json).mod_version
cd minecraft
./gradlew.bat build copyReleaseMods "-Pversion=$version" --console=plain
cd ..
python scripts/build_native.py
python -m unittest discover -s tests -v
python scripts/package_release.py
python scripts/verify_package.py
python scripts/smoke_install.py --blender 'C:/path/to/blender.exe'
```

Run `release_metadata.py --ref refs/tags/vX.X.X.X` to assemble stable-name packages
locally. Publishing still requires that tag on main history. Never include accounts,
Minecraft assets/binaries, saves, Gradle caches or personal configuration in `dist`.

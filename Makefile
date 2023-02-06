# Run with ARCHES="arch1 arch2" to build for a smaller set of
# architectures.
ARCHES ?= \
	armeabi-v7a \
	arm64-v8a \
	x86 \
	x86_64
export ARCHES

ARCH_OPTIONS := $(foreach arch,$(ARCHES),--arch=$(arch))

OSNAME := $(shell uname -s)

ifeq ($(OSNAME), Darwin)
	PLATFORM := macosx
else
	PLATFORM := linux
endif

ANDROID_API := 31
ANDROIDNDKVER := 23.2.8568313

SDK := ${ANDROID_HOME}/android-sdk-$(PLATFORM)

ADB := adb
DOCKER := docker
P4A := p4a
PODMAN := podman
PYTHON_FOR_ANDROID := python-for-android
TOOLBOX := toolbox

# This checks if an environment variable with a specific name
# exists. If it doesn't, it prints an error message and exits.
# For example to check for the presence of the ANDROIDSDK environment
# variable, you could use:
# make guard-ANDROIDSDK
guard-%:
	@ if [ "${${*}}" = "" ]; then \
		echo "Environment variable $* not set"; \
		exit 1; \
	fi

needs-android-dirs:
	$(MAKE) guard-ANDROIDSDK
	$(MAKE) guard-ANDROIDNDK

# Clear out apks
clean:
	- rm -rf dist/*.apk dist/*.aab dist/version.json src/kolibri tmpenv

deepclean: clean
	$(PYTHON_FOR_ANDROID) clean_dists
	rm -r dist || true
	yes y | $(DOCKER) system prune -a || true
	rm build_docker 2> /dev/null

.PHONY: clean-whl
clean-whl:
	rm -rf whl
	mkdir whl

.PHONY: get-whl
get-whl: clean-whl
	wget -O whl/kolibri.whl "${whl}"

# Extract the whl file
src/kolibri: clean
	rm -r src/kolibri 2> /dev/null || true
	unzip -qo whl/kolibri.whl "kolibri/*" -x "kolibri/dist/py2only*" -d src/
	# Cleanup:
	./scripts/cleanup-unused-locales.py -l \
	src/kolibri/locale \
	src/kolibri/dist/django/conf/locale \
	src/kolibri/dist/django/contrib/admin/locale \
	src/kolibri/dist/django/contrib/admindocs/locale \
	src/kolibri/dist/django/contrib/auth/locale \
	src/kolibri/dist/django/contrib/contenttypes/locale \
	src/kolibri/dist/django/contrib/flatpages/locale \
	src/kolibri/dist/django/contrib/gis/locale \
	src/kolibri/dist/django/contrib/humanize/locale \
	src/kolibri/dist/django/contrib/postgres/locale \
	src/kolibri/dist/django/contrib/redirects/locale \
	src/kolibri/dist/django/contrib/sessions/locale \
	src/kolibri/dist/django/contrib/sites/locale \
	src/kolibri/dist/django_filters/locale \
	src/kolibri/dist/mptt/locale \
	src/kolibri/dist/rest_framework/locale
	rm -rf \
	src/kolibri/dist/cext/cp27 \
	src/kolibri/dist/cext/cp34 \
	src/kolibri/dist/cext/cp35 \
	src/kolibri/dist/cext/cp36 \
	src/kolibri/dist/cext/cp37 \
	src/kolibri/dist/cext/cp38 \
	src/kolibri/dist/cext/*/Windows
	rm -rf \
	src/kolibri/dist/cheroot/test \
	src/kolibri/dist/magicbus/test \
	src/kolibri/dist/colorlog/tests \
	src/kolibri/dist/django_js_reverse/tests \
	src/kolibri/dist/future/tests \
	src/kolibri/dist/ipware/tests \
	src/kolibri/dist/more_itertools/tests \
	src/kolibri/dist/past/tests \
	src/kolibri/dist/sqlalchemy/testing
	find src/kolibri -name '*.js.map' -exec rm '{}' '+'
	# End of cleanup.
	# patch Django to allow migrations to be pyc files, as p4a compiles and deletes the originals
	sed -i 's/if name.endswith(".py"):/if name.endswith(".py") or name.endswith(".pyc"):/g' src/kolibri/dist/django/db/migrations/loader.py
	# Apply kolibri patches
	patch -d src/ -p1 < patches/0001-Add-track-progress-information-to-channelimport.patch

.PHONY: apps-bundle.zip
apps-bundle.zip:
	wget -N https://github.com/endlessm/kolibri-explore-plugin/releases/latest/download/apps-bundle.zip

clean-apps-bundle:
	- rm -rf src/apps-bundle

src/apps-bundle: clean-apps-bundle apps-bundle.zip
	unzip -qo apps-bundle.zip -d src/apps-bundle

.PHONY: collections.zip
collections.zip:
	wget -N https://github.com/endlessm/endless-key-collections/archive/refs/heads/main.zip
	mv main.zip collections.zip

clean-collections:
	- rm -rf src/collections

src/collections: clean-collections collections.zip
	unzip -qo collections.zip
	mv endless-key-collections-main/json/ src/collections
	rm -rf endless-key-collections-main

clean-welcomeScreen:
	- rm -rf assets/welcomeScreen _explore

assets/welcomeScreen: clean-welcomeScreen
	pip install --target=_explore --no-deps kolibri_explore_plugin
	cp -r _explore/kolibri_explore_plugin/welcomeScreen/ assets/

.PHONY: p4a_android_distro
p4a_android_distro: needs-android-dirs
	$(P4A) create $(ARCH_OPTIONS)

.PHONY: needs-version
needs-version: src/kolibri
	$(eval VERSION_NAME ?= $(shell python3 scripts/version.py version_name))
	$(eval VERSION_CODE ?= $(shell python3 scripts/version.py version_code))
	$(eval EK_VERSION ?= $(shell python3 scripts/version.py ek_version))

dist/version.json: needs-version
	mkdir -p dist
	echo '{"versionCode": "$(VERSION_CODE)", "versionName": "$(VERSION_NAME)", "ekVersion": "$(EK_VERSION)"}' > $@

DIST_DEPS = \
	p4a_android_distro \
	src/kolibri \
	src/apps-bundle \
	src/collections \
	assets/welcomeScreen \
	needs-version \
	dist/version.json

.PHONY: kolibri.apk
# Build the signed version of the apk
kolibri.apk: $(DIST_DEPS)
	$(MAKE) guard-P4A_RELEASE_KEYSTORE
	$(MAKE) guard-P4A_RELEASE_KEYALIAS
	$(MAKE) guard-P4A_RELEASE_KEYSTORE_PASSWD
	$(MAKE) guard-P4A_RELEASE_KEYALIAS_PASSWD
	@echo "--- :android: Build APK"
	$(P4A) apk --release --sign $(ARCH_OPTIONS) --version="$(VERSION_NAME)" --numeric-version=$(VERSION_CODE)
	mkdir -p dist
	mv "kolibri-release-$(VERSION_NAME).apk" dist/kolibri-release-$(EK_VERSION).apk

.PHONY: kolibri.apk.unsigned
# Build the unsigned debug version of the apk
kolibri.apk.unsigned: $(DIST_DEPS)
	@echo "--- :android: Build APK (unsigned)"
	$(P4A) apk $(ARCH_OPTIONS) --version="$(VERSION_NAME)" --numeric-version=$(VERSION_CODE)
	mkdir -p dist
	mv "kolibri-debug-$(VERSION_NAME).apk" dist/kolibri-debug-$(EK_VERSION).apk

.PHONY: kolibri.aab
# Build the signed version of the aab
kolibri.aab: $(DIST_DEPS)
	$(MAKE) guard-P4A_RELEASE_KEYSTORE
	$(MAKE) guard-P4A_RELEASE_KEYALIAS
	$(MAKE) guard-P4A_RELEASE_KEYSTORE_PASSWD
	$(MAKE) guard-P4A_RELEASE_KEYALIAS_PASSWD
	@echo "--- :android: Build AAB"
	$(P4A) aab --release --sign $(ARCH_OPTIONS) --version="$(VERSION_NAME)" --numeric-version=$(VERSION_CODE)
	mkdir -p dist
	mv "kolibri-release-$(VERSION_NAME).aab" dist/kolibri-release-$(EK_VERSION).aab

# DOCKER BUILD

# Build the docker image. Should only ever need to be rebuilt if project requirements change.
# Makes dummy file
.PHONY: build_docker
build_docker: Dockerfile
	$(DOCKER) build -t android_kolibri .

# Run the docker image.
# TODO Would be better to just specify the file here?
run_docker: build_docker
	env DOCKER="$(DOCKER)" ./scripts/rundocker.sh

# Toolbox build
build_toolbox: Dockerfile-toolbox
	$(PODMAN) build -t android_kolibri_toolbox -f $< .
	$(TOOLBOX) rm -f android_kolibri || :
	$(TOOLBOX) create -c android_kolibri -i android_kolibri_toolbox

install:
	$(ADB) uninstall org.endlessos.Key || true 2> /dev/null
	$(ADB) install dist/*-debug-*.apk

logcat:
	$(ADB) logcat | grep -i -E "python|kolibr| `$(ADB) shell ps | grep ' org.endlessos.Key$$' | tr -s [:space:] ' ' | cut -d' ' -f2` " | grep -E -v "WifiTrafficPoller|localhost:5000|NetworkManagementSocketTagger|No jobs to start"

$(SDK)/cmdline-tools/latest/bin/sdkmanager:
	@echo "Downloading Android SDK command line tools"
	wget https://dl.google.com/android/repository/commandlinetools-$(PLATFORM)-7583922_latest.zip
	rm -rf cmdline-tools
	unzip commandlinetools-$(PLATFORM)-7583922_latest.zip
# This is unfortunate since it will download the command line tools
# again, but after this it will be properly installed and updatable.
	yes y | ./cmdline-tools/bin/sdkmanager "cmdline-tools;latest" --sdk_root=$(SDK)
	rm -rf cmdline-tools
	rm commandlinetools-$(PLATFORM)-7583922_latest.zip

sdk: $(SDK)/cmdline-tools/latest/bin/sdkmanager
	yes y | $(SDK)/cmdline-tools/latest/bin/sdkmanager "platform-tools"
	yes y | $(SDK)/cmdline-tools/latest/bin/sdkmanager "platforms;android-$(ANDROID_API)"
	yes y | $(SDK)/cmdline-tools/latest/bin/sdkmanager "system-images;android-$(ANDROID_API);default;x86_64"
	yes y | $(SDK)/cmdline-tools/latest/bin/sdkmanager "build-tools;30.0.3"
	yes y | $(SDK)/cmdline-tools/latest/bin/sdkmanager "ndk;$(ANDROIDNDKVER)"
	ln -sfT ndk/$(ANDROIDNDKVER) $(SDK)/ndk-bundle
	@echo "Accepting all licenses"
	yes | $(SDK)/cmdline-tools/latest/bin/sdkmanager --licenses

# All of these commands are non-destructive, so if the cmdline-tools are already installed, make will skip
# based on the directory existing.
# The SDK installations will take a little time, but will not attempt to redownload if already installed.
setup:
	$(MAKE) guard-ANDROID_HOME
	$(MAKE) sdk
	@echo "Make sure to set the necessary environment variables"
	@echo "export ANDROIDSDK=$(SDK)"
	@echo "export ANDROIDNDK=$(SDK)/ndk-bundle"

clean-tools:
	rm -rf ${ANDROID_HOME}

// Jenkins pipeline
// https://www.jenkins.io/doc/book/pipeline/
pipeline {
    agent {
        dockerfile {
            // Try to use the same node to make use of caching.
            reuseNode true
        }
    }

    environment {
        // URL for the Kolibri wheel to include.
        // FIXME: It would be nice to cache this somehow.
        // FIXME: Go back to use an official release once that happens on GitHub for 0.16.
        KOLIBRI_WHL_URL = 'https://github.com/learningequality/kolibri/releases/download/v0.16.0-alpha14/kolibri-0.16.0a14-py2.py3-none-any.whl'

        // Both p4a and gradle cache outputs in the home directory.
        // Point it inside the workspace.
        HOME = "$WORKSPACE/_cache"
    }


    options {
        ansiColor('xterm')

        // This is needed to allow the upload job to copy the built
        // artifacts.
        copyArtifactPermission('kolibri-installer-android-upload')
    }

    stages {
        stage('Kolibri wheel') {
            steps {
                sh 'make get-whl whl="$KOLIBRI_WHL_URL"'
            }
        }

        stage('Distro') {
            steps {
                // p4a's cache invalidation has tons of bugs. Clean the
                // builds and distributions to ensure we get all the
                // current code copied into it.
                sh 'p4a clean builds'
                sh 'p4a clean dists'
                sh 'make p4a_android_distro'
            }
        }

        stage('Debug APK') {
            steps {
                sh 'make kolibri.apk.unsigned'
                archiveArtifacts artifacts: 'dist/*.apk, dist/version.json'
            }
        }

        stage('Release AAB') {
            // Don't build the release AAB for PRs.
            when {
                expression { !params.ghprbPullId }
            }

            steps {
                withCredentials(
                    [[$class: 'VaultCertificateCredentialsBinding',
                      credentialsId: 'google-play-upload-key',
                      keyStoreVariable: 'P4A_RELEASE_KEYSTORE',
                      passwordVariable: 'P4A_RELEASE_KEYSTORE_PASSWD']]
                ) {
                    // p4a expects a couple more environment variables
                    // related to the key alias within the keystore.
                    withEnv(
                        ['P4A_RELEASE_KEYALIAS=upload',
                         "P4A_RELEASE_KEYALIAS_PASSWD=$P4A_RELEASE_KEYSTORE_PASSWD"]
                    ) {
                        sh 'make kolibri.aab'
                        archiveArtifacts artifacts: 'dist/*.aab'
                    }
                }
            }
        }
    }

    post {
        failure {
            // Send email on failures when this not a PR. Unfortunately,
            // there's no declarative pipeline step to test for this
            // besides wrapping in a script block and checking for one
            // of the ghprb environment variables.
            script {
                if (!env.ghprbPullId) {
                    emailext (
                        to: 'apps@endlessos.org,$DEFAULT_RECIPIENTS',
                        replyTo: 'apps@endlessos.org',
                        subject: '$DEFAULT_SUBJECT',
                        body: '$DEFAULT_CONTENT',
                    )
                }
            }
        }
    }
}

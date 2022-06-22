// Jenkins pipeline
// https://www.jenkins.io/doc/book/pipeline/
pipeline {
    agent {
        dockerfile {
            // We're trying to recreate what rundocker.sh does. Jenkins
            // will already run as the Jenkins user with the checkout
            // mounted and set to the current workdir. What we need is
            // to mount the cache volume at the expected location and
            // set HOME to that path.
            args '--mount type=volume,src=kolibri-android-cache,dst=/cache ' +
                '--env HOME=/cache'

            // Try to use the same node to make use of caching.
            reuseNode true
        }
    }

    environment {
        // URL for the Kolibri wheel to include.
        // FIXME: It would be nice to cache this somehow.
        KOLIBRI_WHL_URL = 'https://github.com/learningequality/kolibri/releases/download/v0.15.1/kolibri-0.15.1-py2.py3-none-any.whl'
    }


    options {
        ansiColor('xterm')
    }

    stages {
        stage('Kolibri wheel') {
            steps {
                sh 'make get-whl whl="$KOLIBRI_WHL_URL"'
            }
        }

        stage('Distro') {
            steps {
                sh 'make p4a_android_distro'
            }
        }

        stage('Debug APK') {
            steps {
                sh 'make kolibri.apk.unsigned'
                archiveArtifacts artifacts: 'dist/*.apk'
            }
        }

        stage('Release AAB') {
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

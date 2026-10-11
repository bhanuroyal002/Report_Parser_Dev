def notifyReportParserWebhook(String status) {
    if (!env.REPORT_PARSER_WEBHOOK_URL?.trim()) {
        echo 'Webhook not configured; skipping external deployment notification.'
        return
    }

    withEnv(["REPORT_PARSER_NOTIFY_STATUS=" + status]) {
        sh '''
            set +x
            payload="$(python3 -c 'import json, os; s=os.environ["REPORT_PARSER_NOTIFY_STATUS"]; print(json.dumps({"text": "Report Parser deployment " + s + ": " + os.environ.get("JOB_NAME", "Jenkins job") + " #" + os.environ.get("BUILD_NUMBER", ""), "status": s, "job": os.environ.get("JOB_NAME", ""), "buildNumber": os.environ.get("BUILD_NUMBER", ""), "buildUrl": os.environ.get("BUILD_URL", "")}))')"
            if ! curl --silent --show-error --fail --max-time 8 \
                -H 'Content-Type: application/json' \
                --data-binary "$payload" "$REPORT_PARSER_WEBHOOK_URL"; then
                echo "WARNING: webhook notification failed; Jenkins build status is unchanged."
            fi
        '''
    }
}

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '5'))
        timeout(time: 30, unit: 'MINUTES')
    }

    environment {
        APP_DIR = '/opt/report_parser'
        SERVICE_NAME = 'report-parser'
        APP_URL = 'http://127.0.0.1:8080'
        ARTIFACT = "report-parser-${BUILD_NUMBER}.tar.gz"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate') {
            steps {
                sh '''
                    set -eux
                    python3 --version
                    python3 -m py_compile app.py parser.py history.py report_builder.py
                    bash -n deploy/install-server.sh deploy/report-parser-deploy.sh deploy/report-parser-healthcheck.sh
                    test -f requirements.txt
                    test -f gunicorn.conf.py
                    test -f deploy/report-parser-healthcheck.service
                    test -f deploy/report-parser-healthcheck.timer
                '''
            }
        }

        stage('Build') {
            steps {
                sh '''
                    set -eux
                    rm -rf .ci-venv
                    python3 -m venv .ci-venv
                    .ci-venv/bin/python -m pip install --upgrade pip
                    .ci-venv/bin/pip install -r requirements.txt
                    .ci-venv/bin/pip check
                '''
            }
        }

        stage('Package') {
            steps {
                sh '''
                    set -eux
                    # Write the archive outside the directory being archived.
                    # Creating it in WORKSPACE changes the root directory mtime while tar reads it.
                    PACKAGE_TMP="$WORKSPACE@tmp/$ARTIFACT"
                    mkdir -p "$WORKSPACE@tmp"
                    rm -f "$PACKAGE_TMP" "$ARTIFACT"
                    tar -czf "$PACKAGE_TMP" \
                        --exclude='./.git' \
                        --exclude='./.venv' \
                        --exclude='./.ci-venv' \
                        --exclude='./data' \
                        --exclude='./.env' \
                        --exclude='./__pycache__' \
                        --exclude='./.pytest_cache' \
                        --exclude='./report-parser-*.tar.gz' \
                        -C "$WORKSPACE" .
                    cp "$PACKAGE_TMP" "$WORKSPACE/$ARTIFACT"
                    if tar -tzf "$ARTIFACT" | grep -E '(^|/)(report-parser-[^/]*\.tar\.gz|__pycache__|\.ci-venv)(/|$)'; then
                        echo "ERROR: generated files were included in the deployment package."
                        exit 1
                    fi
                    tar -tzf "$ARTIFACT" | head -40
                '''
                archiveArtifacts artifacts: "${ARTIFACT}", fingerprint: true, onlyIfSuccessful: true
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    set -eux
                    sudo -n /usr/local/sbin/report-parser-deploy "$WORKSPACE/$ARTIFACT"
                '''
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                    set -eux
                    for attempt in 1 2 3 4 5 6 7 8 9 10; do
                        if curl --fail --silent --show-error "$APP_URL/healthz" >/dev/null && \
                           curl --fail --silent --show-error "$APP_URL/" >/dev/null; then
                            echo "Report Parser health endpoint and home page are healthy."
                            exit 0
                        fi
                        sleep 2
                    done
                    echo "Report Parser health check failed."
                    sudo systemctl --no-pager --full status "$SERVICE_NAME" || true
                    exit 1
                '''
            }
        }
    }

    post {
        success {
            echo 'Report Parser deployment completed successfully.'
            script { notifyReportParserWebhook('SUCCESS') }
        }
        failure {
            echo 'Report Parser deployment failed. Check the failed stage and service logs.'
            script { notifyReportParserWebhook('FAILURE') }
        }
    }
}

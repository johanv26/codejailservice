import os
import json
import logging
import sys
import timeit

from codejail import jail_code

from copy import deepcopy
from flask import Flask, Response, jsonify, request
from logging.config import dictConfig


dictConfig({
    'version': 1,
    'formatters': {
        'default': {
            'format': '%(asctime)s %(levelname)s %(process)d ' '[%(name)s] %(filename)s:%(lineno)d - %(message)s',
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'default'
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console']
    }
})

app = Flask(__name__)
env_config = os.getenv("FLASK_APP_SETTINGS", "codejailservice.config.ProductionConfig")
app.config.from_object(env_config)

def configure_codejail(app):
    code_jail_settings = app.config["CODE_JAIL"]
    python_bin = code_jail_settings.get('python_bin')
    if python_bin:
        user = code_jail_settings['user']
        jail_code.configure("python", python_bin, user=user)
    limits = code_jail_settings.get('limits', {})
    for name, value in limits.items():
        jail_code.set_limit(
            limit_name=name,
            value=value,
        )
    limit_overrides = code_jail_settings.get('limit_overrides', {})
    for context, overrides in limit_overrides.items():
        for name, value in overrides.items():
            jail_code.override_limit(
                limit_name=name,
                value=value,
                limit_overrides_context=context,
            )

configure_codejail(app)

from codejail.safe_exec import SafeExecException, json_safe
from codejail.safe_exec import not_safe_exec as codejail_not_safe_exec
from codejail.safe_exec import safe_exec as codejail_safe_exec

@app.route("/")
def index():
    return Response("Edx Codejail Service", status=200)

@app.route("/health")
def health():
    return Response("OK", status=200)

@app.post("/api/v0/code-exec")
def code_exec():
    payload = json.loads(request.form["payload"])
    globals_dict = deepcopy(payload["globals_dict"])

    unsafely = payload["unsafely"]
    if unsafely:
        exec_fn = codejail_not_safe_exec
    else:
        exec_fn = codejail_safe_exec

    try:
        python_path=payload["python_path"]
        if python_path:
            extra_files=[(python_path[0], request.files[python_path[0]].read())]
        else:
            extra_files=[]
        course_id = payload["limit_overrides_context"]
        problem_id = payload["slug"]
        app.logger.info("Running problem_id:%s jailed code for course_id:%s ...", problem_id, course_id)
        start = timeit.default_timer()
        exec_fn(
            payload["code"],
            globals_dict,
            python_path=python_path,
            extra_files=extra_files,
            limit_overrides_context=course_id,
            slug=problem_id,
        )
        end = timeit.default_timer()

    except SafeExecException as e:
        # Saving SafeExecException e in exception to be used later.
        app.logger.error("Error found while executing jailed code.")
        exception = e
        emsg = str(e)
    else:
        app.logger.info("Jailed code was executed in %s seconds.", str(end-start))
        exception = None
        emsg = None

    response = {
        "globals_dict": globals_dict,
        "emsg": emsg
    }

    return jsonify(response)

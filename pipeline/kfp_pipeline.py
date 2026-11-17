"""Kubeflow Pipelines (kfp v2) definition for the same gate idea.

    *** NOT RUN IN THIS REPO. ***
    Running it needs a Google Cloud project, billing, and the Vertex AI and
    BigQuery APIs switched on. Nobody has compiled or run this file here.
    Treat it as a sketch of how the stages connect.

Stages:  preprocess -> train -> evaluate -> gate -> deploy

Data: the public BigQuery table bigquery-public-data.samples.natality
(see DATA.md for the page and the licence). The model is a plain linear
regression that predicts birth weight from a few columns.

kfp is an OPTIONAL import. The tests in this repo never need it. Importing
this module works without kfp. Calling build_pipeline() without kfp raises
a clear error.

The gate step uses gate_decision() below. It is a small, stand-alone copy of
the rule in vertex_gate/gate.py, because a pipeline step cannot import this
repo. tests/test_pipeline.py checks that the two copies agree.
"""

try:  # optional import
    from kfp import compiler, dsl

    KFP_AVAILABLE = True
except ImportError:  # the normal case when running the tests
    compiler = dsl = None
    KFP_AVAILABLE = False

NATALITY_TABLE = "bigquery-public-data.samples.natality"


def gate_decision(candidate_rmse: float, current_rmse: float,
                  has_current: bool, margin: float) -> str:
    """Return "true" if the model may deploy, else "false". Fails closed.

    Self-contained on purpose: only the standard library, imports inside.
    Lower RMSE is better. A tie is a block. If nothing is deployed yet,
    the first model deploys.
    """
    import math

    def ok(x):
        return (isinstance(x, (int, float)) and not isinstance(x, bool)
                and math.isfinite(x))

    try:
        if not ok(margin) or margin < 0:
            return "false"
        if not has_current:
            return "true"
        if not ok(candidate_rmse) or not ok(current_rmse):
            return "false"
        return "true" if (current_rmse - candidate_rmse) > margin else "false"
    except Exception:
        return "false"


def build_pipeline():
    """Build the pipeline function. Needs kfp. Not run in this repo."""
    if not KFP_AVAILABLE:
        raise RuntimeError(
            "kfp is not installed. Run: pip install kfp  (this file is a "
            "sketch and is not run in this repo)")

    base = "python:3.11"

    @dsl.component(base_image=base,
                   packages_to_install=["google-cloud-bigquery", "pandas",
                                        "db-dtypes", "pyarrow"])
    def preprocess(project: str, rows: int,
                   dataset: dsl.Output[dsl.Dataset]):
        from google.cloud import bigquery

        query = f"""
            SELECT mother_age, gestation_weeks, plurality, weight_pounds
            FROM `bigquery-public-data.samples.natality`
            WHERE weight_pounds IS NOT NULL AND mother_age IS NOT NULL
              AND gestation_weeks IS NOT NULL AND plurality IS NOT NULL
            LIMIT {int(rows)}
        """
        frame = bigquery.Client(project=project).query(query).to_dataframe()
        frame.to_csv(dataset.path, index=False)

    @dsl.component(base_image=base,
                   packages_to_install=["pandas", "scikit-learn", "joblib"])
    def train(dataset: dsl.Input[dsl.Dataset],
              model: dsl.Output[dsl.Model],
              holdout: dsl.Output[dsl.Dataset]):
        import joblib
        import pandas as pd
        from sklearn.linear_model import LinearRegression
        from sklearn.model_selection import train_test_split

        frame = pd.read_csv(dataset.path)
        features = ["mother_age", "gestation_weeks", "plurality"]
        fit, test = train_test_split(frame, test_size=0.2, random_state=0)
        reg = LinearRegression().fit(fit[features], fit["weight_pounds"])
        joblib.dump(reg, model.path)
        test.to_csv(holdout.path, index=False)

    @dsl.component(base_image=base,
                   packages_to_install=["pandas", "scikit-learn", "joblib"])
    def evaluate(model: dsl.Input[dsl.Model],
                 holdout: dsl.Input[dsl.Dataset]) -> float:
        import joblib
        import pandas as pd
        from sklearn.metrics import mean_squared_error

        test = pd.read_csv(holdout.path)
        features = ["mother_age", "gestation_weeks", "plurality"]
        reg = joblib.load(model.path)
        predicted = reg.predict(test[features])
        return float(mean_squared_error(test["weight_pounds"], predicted) ** 0.5)

    gate = dsl.component(base_image=base)(gate_decision)

    @dsl.component(base_image=base,
                   packages_to_install=["google-cloud-aiplatform"])
    def deploy(project: str, region: str, model: dsl.Input[dsl.Model]):
        # Sketch only. A real deploy needs a serving container that matches
        # the saved model format, and an endpoint. Fill those in for your
        # own project.
        from google.cloud import aiplatform

        aiplatform.init(project=project, location=region)
        print("would upload and deploy the model from", model.uri)

    condition = getattr(dsl, "If", None) or dsl.Condition

    @dsl.pipeline(name="vertex-gate-linear-regression")
    def pipeline(project: str, current_rmse: float, has_current: bool,
                 region: str = "us-central1",
                 rows: int = 100000, margin: float = 0.01):
        # current_rmse and has_current have no defaults on purpose. A default
        # of has_current=False would deploy the first model with no comparison.
        prep = preprocess(project=project, rows=rows)
        trained = train(dataset=prep.outputs["dataset"])
        score = evaluate(model=trained.outputs["model"],
                         holdout=trained.outputs["holdout"])
        verdict = gate(candidate_rmse=score.output, current_rmse=current_rmse,
                       has_current=has_current, margin=margin)
        with condition(verdict.output == "true"):
            deploy(project=project, region=region,
                   model=trained.outputs["model"])

    return pipeline


def compile_pipeline(path="vertex_gate_pipeline.yaml"):
    """Compile to a YAML file. Needs kfp. Not run in this repo."""
    compiler.Compiler().compile(build_pipeline(), package_path=path)
    return path


if __name__ == "__main__":
    print("compiled:", compile_pipeline())

"""Denominators, cutoff ties, ranking parity and out-of-time feature contracts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import numpy as np
import pandas as pd

from pipeline.common import PRODUCTS, FEATURE_VERSIONS
from pipeline.evaluate import metrics
from pipeline.train import ranked_products
from track_a.unified_metrics import customer_metrics, top_fraction_weights, ProductMetrics
from track_a.unified_evaluation import PastGroupRates, FrozenRFM, load_cohort, validate_source, digest, run


class MetricContracts(unittest.TestCase):
    def test_constant_scores_have_lift_one_even_with_imbalanced_labels(self):
        counts = np.array([2,1]+[0]*98)
        result = customer_metrics(np.ones(100),counts)
        self.assertAlmostEqual(result["lift10_buyers"],1)
        self.assertAlmostEqual(result["capture10_products"],.1)
        self.assertAlmostEqual(result["AP"],.02)
        self.assertEqual(result["AUC"],.5)

    def test_cutoff_ties_are_fractional_and_independent_of_id_order(self):
        scores = np.array([9,8,8,8,1,1.])
        counts = np.array([0,1,0,2,0,0])
        weights,_ = top_fraction_weights(scores,.5)
        np.testing.assert_allclose(weights,[1,2/3,2/3,2/3,0,0])
        first = customer_metrics(scores,counts,.5)
        order = [5,3,0,4,1,2]
        second = customer_metrics(scores[order],counts[order],.5)
        for column in ["AP","AUC","lift10_buyers","capture10_products","selected_mass"]:
            self.assertAlmostEqual(first[column],second[column])

    def test_perfect_customer_scores_and_count_predictions(self):
        counts = np.array([2,1,0,0])
        result = customer_metrics([.9,.8,.1,0],counts,.5,event_probability=[1,1,0,0],predicted_count=counts)
        for metric,value in [("AP",1),("AUC",1),("lift10_buyers",2),("capture10_products",1),("Brier",0),("RMSE_count",0)]:
            self.assertAlmostEqual(result[metric],value)

    def test_product_metrics_match_existing_pipeline_including_more_than_seven_labels(self):
        rng = np.random.default_rng(42)
        own = rng.integers(0,2,(50,24))
        truth = rng.integers(0,2,(50,24))*(1-own)
        own[0]=1;truth[0]=0
        own[1]=0;truth[1]=1
        scores = rng.integers(0,3,(50,24)).astype(float)
        expected = metrics(truth,ranked_products(scores,own))
        powers = 1 << np.arange(24)
        acc = ProductMetrics()
        for start in range(0,50,13):
            acc.update(scores[start:start+13],own[start:start+13]@powers,truth[start:start+13]@powers)
        actual = acc.result()
        for key,value in expected.items():
            self.assertAlmostEqual(actual[key],value)
        self.assertLess(actual["recall_at_7_buyers_ceiling"],1)
        self.assertAlmostEqual(actual["map_at_7_all_ceiling"],expected["buyer_prevalence"])

    def test_owned_product_cannot_be_a_new_acquisition(self):
        with self.assertRaises(ValueError):
            ProductMetrics().update(np.zeros((1,24)),[1],[1])

    def test_group_scores_use_only_previously_added_outcomes(self):
        history = PastGroupRates(prior=0)
        before,_ = history.predict(np.array(["a","b"]),.2)
        np.testing.assert_allclose(before,[.2,.2])
        history.update(np.array(["a","a","b"]),np.array([1,0,0]))
        after,_ = history.predict(np.array(["a","b"]),.2)
        np.testing.assert_allclose(after,[.5,0])


class UnifiedIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/"fixture_source"
        self.source.mkdir()
        self.months = ["2020-01","2020-02","2020-03","2020-04"]
        config = dict(split=dict(test_origins=["2020-03"]))
        for name,value in [("config.resolved.json",config),("completed.json",dict(status="success")),
                ("input_manifest.json",dict(products=PRODUCTS)),
                ("point_in_time_audit.json",[dict(origin=m,m_max_label_month=m,clv=dict(max_label_month=m)) for m in self.months])]:
            (self.source/name).write_text(json.dumps(value),encoding="utf-8")
        rows = []
        for customer in range(1,9):
            old = None
            total_events = 0
            last_event = None
            for j,month in enumerate(self.months):
                mask = (1 << customer)-1
                for k in range(1,j+1):
                    if (customer+k)%2==0:
                        mask |= 1 << (8+k)
                acquired = None if old is None else mask & ~old
                if acquired:
                    total_events += 1;last_event=j
                rows.append(dict(customer_id=customer,month=month,is_observed=True,product_complete=True,
                    R=None if last_event is None else float(j-last_event),F_event_months=total_events,
                    n_products=mask.bit_count(),rfm_no_event=int(last_event is None),M_group_points=customer*10.,M_group_uses_baseline=0,
                    predicted_acquisitions_1m=.1+customer*.02,clv_unavailable=0,persona_id="P1" if customer<5 else "P5",
                    presence_lifecycle="Active",lifecycle="At-risk" if customer<3 else "Active",
                    owned_mask=mask,acquired_mask=acquired))
                old=mask
        self.database = self.root/"index.duckdb"
        connection = duckdb.connect(str(self.database))
        frame = pd.DataFrame(rows)
        frame["acquired_mask"] = frame.acquired_mask.astype("Int64")
        connection.register("fixture",frame)
        connection.execute("CREATE TABLE snapshots AS SELECT * FROM fixture")
        connection.execute("CREATE TABLE affinity(month VARCHAR,conditional_json VARCHAR,popularity_json VARCHAR)")
        conditional = np.full((24,24),.02);np.fill_diagonal(conditional,0)
        for month in self.months:
            connection.execute("INSERT INTO affinity VALUES (?,?,?)",[month,json.dumps(conditional.tolist()),json.dumps(np.linspace(.01,.1,24).tolist())])
        self.metadata = dict(status="success",index_version=1,source_run=self.source.name,scope="synthetic contracts",months=self.months,
            affinity=dict(method=FEATURE_VERSIONS["affinity"]),
            provenance=dict(source_files_sha256={p.name:digest(p) for p in self.source.iterdir()}))
        connection.execute("CREATE TABLE metadata(value VARCHAR)")
        connection.execute("INSERT INTO metadata VALUES (?)",[json.dumps(self.metadata)])
        connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_common_cohort_excludes_missing_pairs_and_checks_transition_masks(self):
        with duckdb.connect(str(self.database)) as connection:
            connection.execute("UPDATE snapshots SET product_complete=false WHERE customer_id=1 AND month='2020-02'")
            frame,audit = load_cohort(connection,"2020-01")
            self.assertEqual(len(frame),7)
            self.assertEqual(audit["excluded_next_n"],1)
            connection.execute("UPDATE snapshots SET acquired_mask=0 WHERE customer_id=3 AND month='2020-02'")
            with self.assertRaisesRegex(ValueError,"ownership transitions"):
                load_cohort(connection,"2020-01")

    def test_source_rejects_future_feature_labels_even_with_matching_hash(self):
        path = self.source/"point_in_time_audit.json"
        audit = json.loads(path.read_text())
        audit[0]["clv"]["max_label_month"]="2020-02"
        path.write_text(json.dumps(audit))
        self.metadata["provenance"]["source_files_sha256"][path.name]=digest(path)
        with duckdb.connect(str(self.database)) as connection:
            connection.execute("UPDATE metadata SET value=?",[json.dumps(self.metadata)])
            with self.assertRaisesRegex(ValueError,"Future outcomes"):
                validate_source(connection,self.source)

    def test_end_to_end_shared_denominators_and_future_outcome_invariance(self):
        with patch("track_a.unified_report.render_report"):
            run(self.database,self.source,self.root/"first",["2020-02","2020-03"],fit_month="2020-01",min_support=1)
            first = pd.read_csv(self.root/"first/group_rates_by_month.csv")
            with duckdb.connect(str(self.database)) as connection:
                connection.execute("UPDATE snapshots SET owned_mask=owned_mask | (1<<23), acquired_mask=acquired_mask | (1<<23) WHERE customer_id=2 AND month='2020-04'")
            run(self.database,self.source,self.root/"second",["2020-02","2020-03"],fit_month="2020-01",min_support=1)
            second = pd.read_csv(self.root/"second/group_rates_by_month.csv")
        columns=["origin","method","group","n","past_only_predicted_rate"]
        pd.testing.assert_frame_equal(first[columns],second[columns])
        self.assertFalse(first.events.equals(second.events))
        metrics_frame = pd.read_csv(self.root/"first/customer_metrics_by_month.csv")
        for _,part in metrics_frame.groupby("origin"):
            self.assertEqual(part.n_all.nunique(),1)
            self.assertEqual(part.cohort_ids_sha256.nunique(),1)
            self.assertAlmostEqual(part.loc[part.method.eq("historical_population"),"lift10_buyers"].iloc[0],1)
        for path in (self.root/"first").glob("*.csv"):
            self.assertNotIn("customer_id",pd.read_csv(path).columns)


if __name__ == "__main__":
    unittest.main()

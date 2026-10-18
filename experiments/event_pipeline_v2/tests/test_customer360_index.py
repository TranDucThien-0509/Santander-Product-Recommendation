"""Serving full populations must preserve the small-store temporal contracts."""
import json
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import urlopen

import numpy as np
import pandas as pd

from pipeline.common import PRODUCTS
from pipeline.features import affinity
from test_customer360 import fixture
from track_a.customer360 import CustomerStore
from track_a.customer360_index import build_index, IndexedCustomerStore, verify_source
from track_a.serve_customer360 import handler_for


class IndexedCustomerContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        cls.args=list(fixture())
        frames,life,flags=cls.args[:3]
        for month,frame in frames.items():
            # A genuine incomplete flag, not just a contradictory completeness marker.
            frame.loc[5,PRODUCTS[1]]=np.nan
            for col in ["age","renta","antiguedad"]: frame[col]=30.
            frame["canal_entrada"]="test"; frame["segmento"]="test"
        frames["2020-02"].loc[2,PRODUCTS[1:3]]=1
        frames["2020-03"].loc[3,PRODUCTS[4]]=1
        for frame in frames.values(): frame["n_products"]=frame[PRODUCTS].sum(axis=1,min_count=24)
        # A later deceased flag must not gate an earlier month.
        flags.loc[flags.month.eq("2020-03") & flags.customer_id.eq(1),"indfall"]="S"
        cls.small=CustomerStore(*cls.args)
        cls.source=cls.root/"source"; cls.source.mkdir()
        (cls.source/"features").mkdir(); (cls.source/"lifecycle").mkdir()
        cls.cache=cls.root/"cache"; cls.cache.mkdir()
        for month,frame in frames.items():
            q=frame.reset_index(); q["month"]=month
            q.to_parquet(cls.source/"features"/f"{month}.parquet",index=False)
            q.to_parquet(cls.cache/f"{month}.parquet",index=False)
            l=life[month].reset_index(); l["month"]=month
            l.to_parquet(cls.source/"lifecycle"/f"{month}.parquet",index=False)
        # The sample store reads persisted scores; the index recomputes them.
        # Give both the same causal formula for full profile parity.
        affinity_config=dict(data=dict(history_start="2020-01"),meta_models=dict(affinity_window_months=3,affinity_prior=1000.))
        for month,frame in frames.items():
            complete=frame.loc[frame.product_complete.eq(1)]
            scores,_,_=affinity(cls.cache,month,affinity_config,complete)
            for j,product in enumerate(PRODUCTS):
                frame.loc[complete.index,"affinity_"+product]=scores[:,j]
        cls.raw=cls.root/"raw.csv"
        raw=flags.rename(columns={"customer_id":"ncodpers","ind_actividad_cliente":"ind_actividad_cliente"}).copy()
        raw["fecha_dato"]=raw["month"]+"-28"
        raw.drop(columns="month").to_csv(cls.raw,index=False)
        config=dict(data=dict(history_start="2020-01",forecast_month="2020-03"),
            meta_models=dict(affinity_window_months=3,affinity_prior=1000.))
        for name,value in [("config.resolved.json",config),
            ("input_manifest.json",dict(products=PRODUCTS,raw=dict(size=cls.raw.stat().st_size))),
            ("completed.json",dict(status="success")),
            ("point_in_time_audit.json",[dict(origin=m,clv=dict(max_label_month=m)) for m in frames])]:
            (cls.source/name).write_text(json.dumps(value))
        cls.database=cls.root/"customers.duckdb"
        build_index(cls.source,cls.raw,cls.database)
        cls.store=IndexedCustomerStore(cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.store.close(); cls.temp.cleanup()

    def test_snapshots_and_profiles_match_existing_contract(self):
        for month in self.store.months:
            for customer_id in range(1,7):
                self.assertEqual(self.store.snapshot(customer_id,month),self.small.snapshot(customer_id,month))
                if self.small.knows_customer(customer_id,month):
                    actual=self.store.profile(customer_id,month)
                    expected=self.small.profile(customer_id,month)
                    for key in ["source_run","scope"]:
                        actual.pop(key); expected.pop(key)
                    self.assertEqual(actual,expected)
        self.assertFalse(self.store.snapshot(1,"2020-01")["historical_deceased"])
        self.assertTrue(self.store.snapshot(1,"2020-03")["historical_deceased"])

    def test_monthly_pagination_search_and_unknown_are_preserved(self):
        for month in self.store.months:
            self.assertEqual(self.store.acquisitions(month),self.small.acquisitions(month))
            self.assertEqual(self.store.search("1",month),self.small.search("1",month))
        self.assertEqual(self.store.search("6","2020-01"),[])
        self.assertEqual(self.store.acquisitions("2020-02",query="2",page_size=1),
            self.small.acquisitions("2020-02",query="2",page_size=1))
        with self.assertRaises(ValueError): self.store.acquisitions("2020-02",page=999)
        with self.assertRaises(KeyError): self.store.profile(6,"2020-01")

    def test_recomputed_affinity_matches_pipeline_formula_at_each_origin(self):
        config=dict(data=dict(history_start="2020-01"),meta_models=dict(affinity_window_months=3,affinity_prior=1000.))
        for month,frame in self.args[0].items():
            complete=frame.loc[frame.product_complete.eq(1)]
            expected,_,_=affinity(self.cache,month,config,complete)
            actual=np.asarray([[self.store.feature_row(int(cid),month)["affinity_"+p] for p in PRODUCTS] for cid in complete.index])
            np.testing.assert_allclose(actual,expected,rtol=1e-12,atol=1e-12)

    def test_provenance_rejects_checksum_mismatch_and_future_labels(self):
        with self.assertRaisesRegex(ValueError,"CRC32C"):
            verify_source(self.source,self.raw,"wrong")
        path=self.source/"point_in_time_audit.json"
        original=path.read_text()
        try:
            audits=json.loads(original); audits[0]["clv"]["max_label_month"]="2020-02"
            path.write_text(json.dumps(audits))
            with self.assertRaisesRegex(ValueError,"future labels"):
                verify_source(self.source,self.raw)
        finally: path.write_text(original)

    def test_readonly_index_handles_concurrent_http_requests(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),handler_for(self.store))
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        base=f"http://127.0.0.1:{server.server_port}"
        paths=["/api/meta","/api/acquisitions/summary","/api/acquisitions?month=2020-02",
            "/api/profile?id=1&month=2020-01","/api/profile?id=2&month=2020-03"]
        def read(path):
            with urlopen(base+path,timeout=10) as response:
                self.assertEqual(response.headers["Cache-Control"],"no-store")
                return json.load(response)
        try:
            with ThreadPoolExecutor(max_workers=5) as pool:
                results=list(pool.map(read,paths))
            self.assertEqual(results[0]["customer_count"],6)
            self.assertEqual(results[2]["total_customers"],1)
            self.assertFalse(results[3]["current"]["historical_deceased"])
            self.assertEqual(results[4]["recommendations"],[])
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__=="__main__": unittest.main()

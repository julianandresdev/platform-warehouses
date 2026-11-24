import importlib.util
import sys
from pathlib import Path
from datetime import date
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'common'))
sys.path.insert(0,str(ROOT/'batch'))
from batch.daily_report import summarize

class DailyReportContract(TestCase):
    def test_partial_when_warehouse_missing(self):
        d=summarize(date(2026,11,24), {'WH-001':([],[])},['WH-002','WH-003'])
        self.assertEqual(d['status'],'PARTIAL')
    def test_receipt_shipment_adjustment(self):
        moves=[{'type':'RECEIPT','quantity':10,'sku':'A'},
               {'type':'SHIPMENT','quantity':2,'sku':'A'},
               {'type':'ADJUSTMENT','quantity':-1,'sku':'A'}]
        d=summarize(date(2026,11,24), {'WH-001':([],moves)},[])
        self.assertEqual(d['net_change_by_sku']['A'],7)

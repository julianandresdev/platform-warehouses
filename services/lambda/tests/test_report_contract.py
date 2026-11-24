import importlib.util
import io
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

spec=importlib.util.spec_from_file_location("handler_contract",Path(__file__).resolve().parents[1]/"handler.py")
h=importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

class ReportContract(TestCase):
    def test_metadata_and_central(self):
        obj={'report_date':'2026-11-24','total_movements':3}
        s3=MagicMock();s3.get_object.return_value={'Body':io.BytesIO(json.dumps(obj).encode()),'Metadata':{'correlation-id':'req-abc'}}
        mock_http=MagicMock();mock_http.__enter__.return_value.status=201
        with patch.dict(h.os.environ,{'CENTRAL_API_URL':'https://central.test','CENTRAL_API_KEY':'token'}),patch.object(h.urllib.request,'urlopen',return_value=mock_http) as http:
            d=h.procesar_reporte_contrato(s3,'bucket','reports/daily/2026-11-24/summary.json',{})
        self.assertEqual(d['status'],'VALID');self.assertEqual(d['correlation_id'],'req-abc')
        self.assertEqual(d['record_count'],3)
        self.assertIn('metadata/reports/',s3.put_object.call_args.kwargs['Key'])
        self.assertEqual(http.call_args.args[0].get_header('X-api-key'),'token')
    def test_invalid_is_recorded(self):
        s3=MagicMock();s3.get_object.return_value={'Body':io.BytesIO(b'bad'), 'Metadata':{}}
        mock_http=MagicMock();mock_http.__enter__.return_value.status=201
        with patch.dict(h.os.environ,{'CENTRAL_API_URL':'https://central.test','CENTRAL_API_KEY':'token'}),patch.object(h.urllib.request,'urlopen',return_value=mock_http):
            d=h.procesar_reporte_contrato(s3,'bucket','reports/x.json',{})
        self.assertEqual(d['status'],'INVALID')

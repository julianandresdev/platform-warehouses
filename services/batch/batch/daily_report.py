"""Reporte F8 por API, acorde a issue #12. python -m batch.daily_report --date YYYY-MM-DD.
El origen CSV/Batch Fargate anterior se mantiene para preservar evidencias.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import os
import urllib.error
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from common.storage import write_json, client

WAREHOUSES=("WH-001","WH-002","WH-003")


def get_json(url, key, timeout=8):
    req=urllib.request.Request(url, headers={"X-API-Key": key, "Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as res:
        return json.loads(res.read())


def post_json(url, key, data, timeout=8):
    req=urllib.request.Request(url, data=json.dumps(data).encode(), method="POST",headers={"X-API-Key":key,"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as res:
        return json.loads(res.read() or b'{}')


def collect_warehouse(warehouse_id, base_url, key, start_utc, end_utc, fetch=get_json):
    base=base_url.rstrip('/')
    inventories=fetch(base+'/inventory',key)
    movements=[]
    for page in range(1,10001):
        from urllib.parse import urlencode
        query=urlencode({'from':start_utc.isoformat(),'to':end_utc.isoformat(),'page':page,'page_size':100})
        chunk=fetch(base+'/movements?'+query,key)
        if not isinstance(chunk,list):raise ValueError('Respuesta de movimientos invalida')
        movements.extend(chunk)
        if len(chunk)<100:break
    else:raise ValueError('Numero maximo de paginas excedido')
    if not isinstance(inventories,list):raise ValueError('Respuesta inventario invalida')
    return inventories,movements


def summarize(report_date, data, missing):
    by_type=Counter();by_sku=defaultdict(int);top=Counter();per_warehouse={}
    for wh,(inventory,movements) in data.items():
        per_warehouse[wh]={'inventories':len(inventory),'movements':len(movements)}
        for m in movements:
            typ=m['type'];qty=int(m['quantity']);sku=m.get('sku',str(m.get('product_id','unknown')))
            if typ not in {'RECEIPT','SHIPMENT','ADJUSTMENT'}:raise ValueError('Tipo no soportado')
            if typ != 'ADJUSTMENT' and qty<=0:raise ValueError('Cantidad invalida')
            delta=qty if typ!='SHIPMENT' else -qty
            by_type[typ]+=1;by_sku[sku]+=delta;top[sku]+=abs(qty)
    return {'report_date':report_date.isoformat(),'status':'PARTIAL' if missing else 'SUCCEEDED',
            'missing_warehouses':missing,'warehouses':per_warehouse,'movements_by_type':dict(by_type),
            'net_change_by_sku':dict(sorted(by_sku.items())),'top_5':top.most_common(5),
            'total_movements':sum(x['movements'] for x in per_warehouse.values())}


def run(day, *, endpoints=None, bucket=None, key=None, central=None, fetch=get_json, post=post_json, storage=None):
    endpoints=endpoints or {w:os.getenv(w.replace('-','')+'_API_URL','') for w in WAREHOUSES}
    bucket=bucket or os.environ['REPORT_BUCKET'];key=key or os.environ['API_KEY']
    central=central if central is not None else os.getenv('CENTRAL_API_URL','')
    storage=storage or client()
    start=datetime.combine(day,datetime.min.time(),tzinfo=ZoneInfo('America/Bogota')).astimezone(timezone.utc)
    end=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=ZoneInfo('America/Bogota')).astimezone(timezone.utc)
    correlation=str(uuid.uuid4())
    data={};missing=[]
    for warehouse in WAREHOUSES:
        try:
            if not endpoints.get(warehouse):raise ValueError('URL no configurada')
            data[warehouse]=collect_warehouse(warehouse,endpoints[warehouse],key,start,end,fetch)
            year,month=day.strftime('%Y'),day.strftime('%m')
            write_json(bucket,f'warehouses/{warehouse}/{year}/{month}/inventory-{day.isoformat()}.json',
                       {'warehouse_id':warehouse,'report_date':day.isoformat(),'inventory':data[warehouse][0]},
                       correlation_id=correlation,s3=storage)
        except (ValueError,KeyError,TimeoutError,urllib.error.URLError, OSError) as err:
            missing.append(warehouse)
    summary=summarize(day,data,missing)
    summary['correlation_id']=correlation
    report_key=f'reports/daily/{day.isoformat()}/summary.json'
    write_json(bucket,report_key,summary,correlation_id=correlation,s3=storage)
    if not central:
        raise RuntimeError('CENTRAL_API_URL obligatorio: el issue #12 requiere POST /internal/batch-runs')
    post(central.rstrip('/')+'/internal/batch-runs',os.getenv('CENTRAL_API_KEY',key),
         {'report_date':day.isoformat(),'status':summary['status'],'report_s3_key':report_key,
          'correlation_id':correlation,'missing_warehouses':missing})
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--date',type=date.fromisoformat,default=date.today()-timedelta(days=1))
    d=p.parse_args().date
    print(json.dumps(run(d),ensure_ascii=False))

if __name__=='__main__':main()

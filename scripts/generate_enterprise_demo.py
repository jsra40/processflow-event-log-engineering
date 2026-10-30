"""Generate entirely fictional, deterministic multi-source order lifecycle data."""
from pathlib import Path
import csv
import random
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'examples' / 'enterprise_orders'
OUT.mkdir(parents=True, exist_ok=True)
R = random.Random(20261030)
N = 1000
BASE = datetime(2026, 1, 5, 8)

def stamp(t): return t.strftime('%Y-%m-%d %H:%M:%S')
def write(name, cols, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)

orders=[]; payments=[]; warehouse=[]; shipping=[]
for i in range(1,N+1):
    oid=f'ORD-{i:05d}'
    channel=R.choices(['Web','Mobile','Retail'],[.55,.35,.10])[0]
    priority=R.choices(['Standard','Express'],[.78,.22])[0]
    start=BASE+timedelta(minutes=R.randint(0, 60*24*55))
    orders.append(dict(**{'Order ID':oid,'Status':'Order Created','Event Time':stamp(start),'Channel':channel,'Priority':priority}))
    t=start+timedelta(minutes=R.randint(3,90))
    retry=(i%11==0)
    if retry:
        payments.append({'Order ID':oid,'Payment Status':'Payment Failed','Payment Time':stamp(t),'Payment Method':'Card'})
        t+=timedelta(minutes=R.randint(15,180))
    cancelled=(i%17==0)
    if cancelled:
        orders.append({'Order ID':oid,'Status':'Order Cancelled','Event Time':stamp(t+timedelta(minutes=10)),'Channel':channel,'Priority':priority})
        continue
    payments.append({'Order ID':oid,'Payment Status':'Payment Authorized','Payment Time':stamp(t),'Payment Method':R.choice(['Card','Wallet'])})
    t+=timedelta(hours=R.randint(1,15))
    warehouse.append({'Order ID':oid,'Warehouse Activity':'Picking Started','Warehouse Time':stamp(t),'Facility':R.choice(['East','West'])})
    t+=timedelta(hours=R.randint(1,10))
    warehouse.append({'Order ID':oid,'Warehouse Activity':'Quality Check','Warehouse Time':stamp(t),'Facility':'Central'})
    if i%13==0:
        t+=timedelta(minutes=R.randint(20,120))
        warehouse.append({'Order ID':oid,'Warehouse Activity':'Quality Check','Warehouse Time':stamp(t),'Facility':'Central'})
    t+=timedelta(hours=R.randint(1,9))
    warehouse.append({'Order ID':oid,'Warehouse Activity':'Packed','Warehouse Time':stamp(t),'Facility':'Central'})
    t+=timedelta(hours=R.randint(2,18))
    shipping.append({'Order ID':oid,'Shipping Status':'Shipped','Shipping Time':stamp(t),'Carrier':R.choice(['ParcelCo','SwiftShip'])})
    if i%19==0:
        continue  # In-progress shipment: legitimate incomplete case
    t+=timedelta(hours=R.randint(8,35)+(R.randint(30,70) if i%9==0 else 0))
    shipping.append({'Order ID':oid,'Shipping Status':'Out for Delivery','Shipping Time':stamp(t),'Carrier':'ParcelCo'})
    t+=timedelta(hours=R.randint(1,10))
    shipping.append({'Order ID':oid,'Shipping Status':'Delivered','Shipping Time':stamp(t),'Carrier':'ParcelCo'})

write('orders.csv',['Order ID','Status','Event Time','Channel','Priority'],orders)
write('payments.csv',['Order ID','Payment Status','Payment Time','Payment Method'],payments)
write('warehouse.csv',['Order ID','Warehouse Activity','Warehouse Time','Facility'],warehouse)
write('shipping.csv',['Order ID','Shipping Status','Shipping Time','Carrier'],shipping)

# Deliberately corrupt a SEPARATE scenario; never contaminate the clean example.
bad=list(payments)
bad[0]={**bad[0], 'Payment Time':'not-a-date'}
bad[1]={**bad[1], 'Payment Time':''}
write('payments_invalid_demo.csv',['Order ID','Payment Status','Payment Time','Payment Method'],bad)
print('Generated fictional order datasets:')
for name, rows in [('orders.csv',orders),('payments.csv',payments),('warehouse.csv',warehouse),('shipping.csv',shipping),('payments_invalid_demo.csv',bad)]:
    print(f'  {name}: {len(rows):,} rows')

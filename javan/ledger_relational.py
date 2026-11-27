"""Schema v2: per-record ledger storage, preserved original values and audit trail.

The transitional UI still submits a whole document. SQL changes are diffed.
Historical records and line item JSON are preserved without recalculating money.
Inactive records remain in the database; the existing UI hides them.
"""
import json
from datetime import datetime, timezone

TABLES = ('services', 'invoices', 'debts')
SCHEMA = (
    """CREATE TABLE ledger_meta (
      id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL CHECK(revision>=1),
      next_number INTEGER NOT NULL CHECK(next_number>=1), settings_json TEXT NOT NULL,
      logo TEXT, theme TEXT NOT NULL CHECK(theme IN ('light','dark')))""",
    """CREATE TABLE services (
      id TEXT PRIMARY KEY, pos INTEGER NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)),
      name TEXT NOT NULL, price NUMERIC NOT NULL CHECK(price>=0), payload TEXT NOT NULL)""",
    """CREATE TABLE invoices (
      id TEXT PRIMARY KEY, pos INTEGER NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)),
      number TEXT NOT NULL, date TEXT, customer TEXT, payment_status TEXT,
      total NUMERIC NOT NULL CHECK(total>=0), payload TEXT NOT NULL)""",
    "CREATE UNIQUE INDEX invoice_number_active ON invoices(number) WHERE active=1",
    "CREATE INDEX invoice_date_active ON invoices(active,date)",
    """CREATE TABLE invoice_items (
      invoice_id TEXT NOT NULL REFERENCES invoices(id), pos INTEGER NOT NULL,
      name TEXT NOT NULL, price NUMERIC NOT NULL CHECK(price>=0),
      qty NUMERIC NOT NULL CHECK(qty>=0), payload TEXT NOT NULL,
      PRIMARY KEY(invoice_id,pos))""",
    """CREATE TABLE debts (
      id TEXT PRIMARY KEY, pos INTEGER NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)),
      debtor TEXT NOT NULL, amount NUMERIC NOT NULL CHECK(amount>=0),
      paid INTEGER NOT NULL CHECK(paid IN (0,1)), payload TEXT NOT NULL)""",
    "CREATE INDEX debt_status_active ON debts(active,paid)",
    """CREATE TABLE audit_log (
      id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, ts TEXT NOT NULL,
      action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
      before_json TEXT, after_json TEXT)""",
    """CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log
      BEGIN SELECT RAISE(ABORT,'audit log is append-only'); END""",
    """CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log
      BEGIN SELECT RAISE(ABORT,'audit log is append-only'); END""",
)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def canonical_number(value):
    n = str(value)
    return n.lstrip('0') if n.isascii() and n.isdigit() else n


def create_schema(db):
    for statement in SCHEMA:
        db.execute(statement)


def load_relational(db):
    meta = db.execute('SELECT revision,next_number,settings_json,logo,theme FROM ledger_meta WHERE id=1').fetchone()
    if meta is None:
        # No initialized ledger; partial data is corruption, not an empty book.
        if any(db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone() for table in TABLES):
            raise ValueError('فراداده دفتر حسابداری ناقص است.')
        return 0, None
    revision, number, settings, logo, theme = meta
    result = {'services': [], 'invoices': [], 'debts': [], 'nextInvoiceNumber': number,
              'settings': json.loads(settings), 'customLogo': logo, 'theme': theme}
    items = {}
    for invoice_id, payload in db.execute(
        'SELECT i.invoice_id,i.payload FROM invoice_items i JOIN invoices h ON h.id=i.invoice_id WHERE h.active=1 ORDER BY i.invoice_id,i.pos'
    ):
        items.setdefault(invoice_id, []).append(json.loads(payload))
    for table in TABLES:
        for uid, payload in db.execute(f'SELECT id,payload FROM {table} WHERE active=1 ORDER BY pos,id'):
            row = json.loads(payload)
            if table == 'invoices':
                row['items'] = items.get(uid, [])
            result[table].append(row)
    return revision, result


def audit(db, revision, reason, table, uid, before, after):
    if before == after:
        return
    action = ('create' if before is None else 'void' if after is None else 'update')
    db.execute('INSERT INTO audit_log(revision,ts,action,entity,entity_id,before_json,after_json) VALUES(?,?,?,?,?,?,?)',
               (revision, datetime.now(timezone.utc).isoformat(), reason + ':' + action, table, uid,
                None if before is None else dumps(before), None if after is None else dumps(after)))


def sync_table(db, table, old_rows, new_rows, revision, reason):
    old = {row['id']: (pos, row) for pos, row in enumerate(old_rows)}
    new = {row['id']: (pos, row) for pos, row in enumerate(new_rows)}
    for uid in old.keys() - new.keys():
        db.execute(f'UPDATE {table} SET active=0 WHERE id=?', (uid,))
        audit(db, revision, reason, table, uid, old[uid][1], None)
    # Release the active-number constraint for modified headers before swaps.
    # This occurs within the same transaction and cannot be externally observed.
    if table == 'invoices':
        for uid in old.keys() & new.keys():
            if canonical_number(old[uid][1]['invoiceNumber']) != canonical_number(new[uid][1]['invoiceNumber']):
                db.execute('UPDATE invoices SET active=0 WHERE id=?', (uid,))
    for uid, (pos, row) in new.items():
        previous = old.get(uid)
        before = previous[1] if previous else None
        if before == row:
            if previous[0] != pos:
                db.execute(f'UPDATE {table} SET pos=? WHERE id=?', (pos, uid))
            continue
        if table == 'services':
            db.execute("""INSERT INTO services(id,pos,active,name,price,payload) VALUES(?,?,1,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET pos=excluded.pos,active=1,name=excluded.name,
                       price=excluded.price,payload=excluded.payload""",
                       (uid, pos, row['name'], row['price'], dumps(row)))
        elif table == 'invoices':
            header = dict(row)
            line_items = header.pop('items')
            db.execute("""INSERT INTO invoices(id,pos,active,number,date,customer,payment_status,total,payload)
                       VALUES(?,?,1,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET pos=excluded.pos,active=1,
                       number=excluded.number,date=excluded.date,customer=excluded.customer,
                       payment_status=excluded.payment_status,total=excluded.total,payload=excluded.payload""",
                       (uid, pos, canonical_number(row['invoiceNumber']), row.get('date'),
                        row.get('customerName'), row.get('paymentStatus'), row['finalToman'], dumps(header)))
            if before is None or before['items'] != line_items:
                db.execute('DELETE FROM invoice_items WHERE invoice_id=?', (uid,))
                db.executemany('INSERT INTO invoice_items(invoice_id,pos,name,price,qty,payload) VALUES(?,?,?,?,?,?)',
                               [(uid, i, x['name'], x['price'], x['qty'], dumps(x)) for i, x in enumerate(line_items)])
        else:
            db.execute("""INSERT INTO debts(id,pos,active,debtor,amount,paid,payload) VALUES(?,?,1,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET pos=excluded.pos,active=1,debtor=excluded.debtor,
                       amount=excluded.amount,paid=excluded.paid,payload=excluded.payload""",
                       (uid, pos, row['name'], row['amount'], int(row['paid']), dumps(row)))
        audit(db, revision, reason, table, uid, before, row)


def sync_relational(db, old, new, revision, reason):
    for table in TABLES:
        sync_table(db, table, old[table] if old is not None else [], new[table], revision, reason)
    db.execute("""INSERT INTO ledger_meta(id,revision,next_number,settings_json,logo,theme) VALUES(1,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,next_number=excluded.next_number,
               settings_json=excluded.settings_json,logo=excluded.logo,theme=excluded.theme""",
               (revision, new['nextInvoiceNumber'], dumps(new['settings']), new['customLogo'], new['theme']))
    fields = ('nextInvoiceNumber', 'settings', 'theme', 'customLogo')
    # Avoid duplicating a large logo in audit rows; record its digest instead.
    from hashlib import sha256
    def metadata(data):
        if data is None:
            return None
        value = {k: data[k] for k in fields if k != 'customLogo'}
        value['logo_sha256'] = sha256(data['customLogo'].encode()).hexdigest() if data['customLogo'] else None
        return value
    audit(db, revision, reason, 'meta', '1', metadata(old), metadata(new))

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness(legacy = {}, overrides = {}) {
  const html = fs.readFileSync(path.join(__dirname, '..', 'assets', 'accounting', 'index.html'), 'utf8');
  const script = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
    .map(m => m[1]).find(s => s.includes('function loadStorage'));
  assert.ok(script, 'accounting script found');
  const elements = new Map(), archived = [], saves = [], notices = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {textContent: '', hidden: true, style: {},
      innerHTML: '', classList:{add(){},remove(){}}, appendChild(el){notices.push(el.textContent);}});
    return elements.get(id);
  }
  const bridge = {
    load(cb){cb(JSON.stringify({ok:true,revision:0,data:null}));},
    archiveLegacy(raw,cb){archived.push(JSON.parse(raw));cb('{"ok":true}');},
    save(revision,raw,reason,cb){saves.push({revision, data:JSON.parse(raw), reason});cb(JSON.stringify({ok:true,revision:revision+1,warning:''}));},
    ...overrides
  };
  const context = vm.createContext({
    console, Intl, Date, JSON, Math, window:{}, qt:{webChannelTransport:{}},
    QWebChannel: function(transport, cb){cb({objects:{ledger:bridge}});},
    document:{getElementById:element, createElement(){return {style:{},remove(){}};},
      documentElement:{dataset:{},setAttribute(){}}, body:{inert:false}, addEventListener(){}},
    localStorage:{getItem(k){return Object.hasOwn(legacy,k) ? legacy[k] : null;},
      setItem(){throw Error('legacy must not be overwritten');},removeItem(){throw Error('legacy must not be removed');}},
    setTimeout(){return 1;}, clearTimeout(){}
  });
  const instrumented = script.replace(/\}\)\(\);\s*$/, 'globalThis.api = {state, KEYS, loadStorage, persist, snapshot, computeTotals, isValidJalaliDate, gregorianToJalali, safeRows, safeLogo, safeCounter, numberToPersianWords}; })();');
  assert.notEqual(script, instrumented);
  vm.runInContext(instrumented, context, {filename:'accounting-inline.js'});
  return {api:context.api, elements, archived, saves, notices};
}

const invoice = {id:'i1', invoiceNumber:'1001', customerName:'آزمون',
  date:'1405/09/01',items:[{name:'خدمت',price:1000,qty:2}],
  subtotal:2000,discountAmount:0,finalToman:2000,finalRial:20000};

test('valid Jalali dates and invalid day/month/leap boundaries', () => {
  const {api}=harness();
  for (const d of ['1403/12/30','1405/06/31','1405/07/30','1405/01/01']) assert.equal(api.isValidJalaliDate(d),true,d);
  for (const d of ['1405/13/01','1405/00/10','1405/07/31','1405/12/30','1405/01/00']) assert.equal(api.isValidJalaliDate(d),false,d);
});

test('integer totals, percentage rounding and words', () => {
  const {api}=harness();
  const t=api.computeTotals([{price:1000,qty:3},{price:333,qty:1}],'percent',10);
  assert.equal(t.subtotal,3333);
  assert.equal(t.discountAmount,333);
  assert.equal(t.finalToman,3000);
  assert.equal(t.finalRial,30000);
  assert.equal(api.numberToPersianWords(3000),'سه هزار');
});

test('corrupt legacy services does not discard invoices or write anything', async () => {
  const h=harness({javan_acc_services_v2:'bad JSON',javan_acc_invoices_v2:JSON.stringify([invoice])});
  await h.api.loadStorage();
  assert.equal(h.api.state.invoices.length,1);
  assert.equal(h.archived[0].javan_acc_services_v2,'bad JSON');
  assert.equal(h.saves.length,0);
  assert.equal(await h.api.persist(),false);
  assert.equal(h.saves.length,0);
});

test('empty service catalog and historical totals are migrated as stored', async () => {
  const historical={...invoice,finalToman:1500.5,finalRial:15005};
  const h=harness({javan_acc_services_v2:'[]',javan_acc_invoices_v2:JSON.stringify([historical])});
  await h.api.loadStorage();
  assert.equal(h.saves.length,1);
  assert.equal(h.saves[0].reason,'migration');
  assert.equal(h.saves[0].data.services.length,0);
  assert.equal(h.saves[0].data.invoices[0].finalToman,1500.5);
  assert.equal(h.saves[0].data.nextInvoiceNumber,1002);
});

test('native failure rolls back committed data and keeps invoice draft', async () => {
  let calls=0;
  const h=harness({}, {save(rev,raw,reason,cb){
    calls++;
    cb(JSON.stringify(calls===1?{ok:true,revision:1,warning:''}:{ok:false,error:'disk full'}));
  }});
  await h.api.loadStorage();
  h.api.state.invoice.customerName='draft';
  h.api.state.invoices.push(invoice);
  assert.equal(await h.api.persist(),false);
  assert.equal(h.api.state.invoices.length,0);
  assert.equal(h.api.state.invoice.customerName,'draft');
  assert.ok(h.elements.get('storage-banner').textContent.includes('disk full'));
});

test('unsafe logo and malformed import records rejected', () => {
  const {api}=harness();
  assert.throws(()=>api.safeLogo('data:image/png;base64," onerror="evil'));
  assert.throws(()=>api.safeRows([{...invoice,items:[{name:'x',price:'<img>',qty:1}]}],'invoices'));
  assert.throws(()=>api.safeRows([invoice,invoice],'invoices'));
});

test('new invoice counter reconciles historical maximum',()=>{
  const {api}=harness();
  assert.equal(api.safeCounter(1001,[{invoiceNumber:'2000'}]),2001);
});

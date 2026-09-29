from pathlib import Path
from playwright.sync_api import sync_playwright
import json
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'tests/artifacts/browser';OUT.mkdir(parents=True,exist_ok=True)
results=[];errors=[]
def check(name,condition=True):
 assert condition,name
 results.append(name);print('PASS',name,flush=True)
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True,executable_path=__import__('os').environ.get('SCM_BROWSER') or __import__('shutil').which('chromium'),args=['--no-sandbox'])
 page=b.new_page(viewport={'width':1440,'height':1000},locale='ko-KR')
 page.on('pageerror',lambda e:errors.append(str(e)));requests=[];page.on('request',lambda req:requests.append(req.url))
 direct=False
 page.set_content((ROOT/'site/index.html').read_text(),wait_until='load')
 page.wait_for_function('window.SCM_DEBUG && !SCM_DEBUG.state.busy');page.wait_for_timeout(100)
 page.evaluate("SCMOffline.reset();SCM_DEBUG.refresh(true)");page.wait_for_function('!SCM_DEBUG.state.busy')
 page.select_option('#refreshRate','0')
 check('standalone demo loaded')
 for v in ['overview','inbound','shipment','inventory','targets']:
  page.locator(f'.primary-nav [data-view="{v}"]').click();page.wait_for_timeout(100)
  check('view '+v,page.locator('.view:visible').count()==1 and page.locator('#'+v+'View').is_visible())
 # Manual CRUD and actual preview.
 page.locator('#tgtNewBtn').click();page.locator('#mtName').fill('QA 목표');page.locator('#mtValue').fill('123456');page.locator('#mtPriority').fill('0')
 page.locator('[data-preview]').click();page.wait_for_timeout(100)
 check('target preview', '매칭' in page.locator('#mtPreview').inner_text())
 page.locator('#targetEditor [type="submit"]').click();page.wait_for_timeout(350)
 check('target created',page.locator('#tgtTableBody').get_by_text('QA 목표',exact=True).count()==1)
 row=page.locator('#tgtTableBody tr').filter(has_text='QA 목표');row.locator('[data-target-action="copy"]').click()
 page.locator('#mtName').fill('QA 복사');page.locator('#targetEditor [type="submit"]').click();page.wait_for_timeout(250)
 check('target copied as create',page.locator('#tgtTableBody').get_by_text('QA 복사',exact=True).count()==1)
 row=page.locator('#tgtTableBody tr').filter(has_text='QA 목표');row.locator('[data-target-action="edit"]').click();page.locator('#mtValue').fill('654321');page.locator('#targetEditor [type="submit"]').click();page.wait_for_timeout(250)
 check('target edited', '654,321' in page.locator('#tgtTableBody tr').filter(has_text='QA 목표').inner_text())
 row=page.locator('#tgtTableBody tr').filter(has_text='QA 목표');row.locator('[data-target-action="toggle"]').click();page.wait_for_timeout(200)
 check('target disabled',page.evaluate("SCMOffline.request('/api/targets').targets.find(x=>x.target_name==='QA 목표').enabled===false"))
 page.on('dialog',lambda dlg:dlg.accept())
 page.locator('#tgtTableBody tr').filter(has_text='QA 복사').locator('[data-target-action="del"]').click();page.wait_for_timeout(250)
 check('target deleted',page.locator('#tgtTableBody').get_by_text('QA 복사',exact=True).count()==0)
 # Focus management accessible even if zero registrations.
 page.locator('.primary-nav [data-view="overview"]').click();page.locator('#focusSection_overview [data-focus-manage]').click()
 page.select_option('#focusType','customer');page.locator('#focusCustomerCode').fill('DEMO-C01');page.locator('#focusLabel').fill('QA 거래선');page.locator('#focusAddSubmitBtn').click();page.wait_for_timeout(300)
 check('focus added',page.locator('#focusManageRows').get_by_text('QA 거래선',exact=True).count()==1)
 page.locator('#focusManageRows tr').filter(has_text='QA 거래선').locator('[data-focus-delete]').click();page.wait_for_timeout(250)
 check('focus deleted once',page.locator('#focusManageRows').get_by_text('QA 거래선',exact=True).count()==0)
 page.locator('#focusDialog .dialog-footer [data-close-focus-dialog]').click()
 # All metrics render and hourly sums agree with KPI.
 for metric in ['EA','EQ_DRAM','EQ_FLASH','BOX','USD']:
  page.locator(f'[data-metric="{metric}"]').click();page.wait_for_function('!SCM_DEBUG.state.busy');page.wait_for_timeout(100)
  check('metric '+metric,page.evaluate(f"SCM_DEBUG.state.data.kpi.metric==='{metric}'"))
  eq=page.evaluate("(()=>{const s=SCM_DEBUG.state.data;const a=s.kpi.shipment.actual_today;const h=s.hourly.shipment.reduce((a,b)=>a+(b||0),0);return a===null||Math.abs(a-h)<0.01;})()")
  check('hourly reconciles '+metric,eq)
 # Common item/customer filter input does not throw.
 page.locator('[data-metric="EA"]').click();page.wait_for_function('!SCM_DEBUG.state.busy')
 page.locator('#filterToggle').click();page.locator('#filterItem').fill('DEMO-001-MEMORY');page.wait_for_function("!SCM_DEBUG.state.busy && SCM_DEBUG.state.filters.item==='DEMO-001-MEMORY'")
 check('item text filter active','DEMO-001-MEMORY' in page.locator('#filterChips').inner_text())
 check('filtered chart reconciles',page.evaluate('Math.abs(SCM_DEBUG.state.data.kpi.production.actual_today-SCM_DEBUG.state.data.hourly.production.reduce((a,b)=>a+b,0))<.001'))
 page.locator('#resetFilters').click();page.wait_for_function('!SCM_DEBUG.state.busy');page.locator('#filterToggle').click()
 page.locator('[data-cumulative="overviewChart"]').click();page.locator('[data-zoom="overviewChart"]').click();page.locator('[data-chart-table="overviewChart"]').click()
 check('chart data table',page.locator('#chartDialog tbody tr').count()>0)
 with page.expect_download() as download:page.locator('#exportChart').click()
 download.value.save_as(OUT/'chart.csv');check('CSV BOM',(OUT/'chart.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
 page.locator('#chartDialog .dialog-footer [data-close-dialog]').click();page.locator('[data-cumulative="overviewChart"]').click();page.locator('[data-zoom="overviewChart"]').click()
 check('desktop no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
 page.screenshot(path=str(OUT/'preview-light.png'),full_page=True)
 page.locator('#themeToggle').click();check('dark theme',page.evaluate("document.documentElement.dataset.theme==='dark'"));page.screenshot(path=str(OUT/'preview-dark.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
 check('mobile no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
 page.screenshot(path=str(OUT/'preview-mobile.png'),full_page=True)
 if direct:
  page.reload();page.wait_for_function('window.SCM_DEBUG && !SCM_DEBUG.state.busy')
  check('browser-only target persists',page.evaluate("SCMOffline.request('/api/targets').targets.some(t=>t.target_name==='QA 목표')"))
 check('no JavaScript errors',not errors)
 check('no API/external network in static demo',not [x for x in requests if x.startswith(('http:','https:'))])
 b.close()
(OUT/'results.json').write_text(json.dumps({'passed':len(results),'checks':results,'errors':errors,'direct_file':direct},ensure_ascii=False,indent=2))
print('BROWSER',len(results),'PASS; direct_file=',direct)

#!/usr/bin/env python3
"""Real browser memory controls against the named synthetic preview only.

Uses saved real-model continuation from the manual acceptance chat, not mocked
API/model replies. Mutates disposable preferences/project/task history only.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or not args.output.is_absolute():parser.error('fresh private output required')
    os.umask(0o077);args.output.mkdir(parents=True,mode=0o700)
    origin='http://127.0.0.1:8878'
    report={'synthetic_only':True,'origin':origin,'checks':{}}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
            chromium_sandbox=True,args=['--disable-background-networking'])
        context=browser.new_context(viewport={'width':1365,'height':1000})
        external=[];errors=[]
        def local_only(route):
            url=urlsplit(route.request.url)
            if url.scheme in {'http','https'} and url.netloc!='127.0.0.1:8878':
                external.append(route.request.url);route.abort()
            else:route.continue_()
        context.route('**/*',local_only)
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(origin+'/#chat-home');expect(page.locator('#chat-status')).to_contain_text('جاهزة',timeout=15000)
        page.locator('#chat-memory-manager > summary').click()
        option=page.locator('#chat-conversations option').filter(has_text='What remains unfinished?')
        assert option.count()==1,'saved_real_model_continuation_missing'
        page.locator('#chat-conversations').select_option(option.get_attribute('value'))
        expect(page.locator('#chat-messages')).to_contain_text('UI-841')
        report['checks']['saved_real_model_cross_chat_recall']=True
        page.locator('#chat-memory-manager > summary').click()
        page.screenshot(path=str(args.output/'desktop-continuation.png'))
        for width,height in [(390,844),(768,1024)]:
            page.set_viewport_size({'width':width,'height':height})
            assert page.evaluate('innerWidth')==width,'unreliable_viewport_emulation'
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'horizontal_overflow'
            box=page.locator('#chat-input').bounding_box()
            assert box and box['x']>=0 and box['x']+box['width']<=width and box['y']+box['height']<=height
            page.screenshot(path=str(args.output/f'chat-{width}.png'))
        report['checks']['mobile_and_tablet_fit']=True
        page.set_viewport_size({'width':1365,'height':1000})
        page.locator('#chat-memory-manager > summary').click()
        row=page.locator('#chat-memory-list article').filter(has_text='communication.style:')
        before_revision=0
        if row.count():
            import re
            before_revision=int(re.search(r'\bv(\d+)\b',row.inner_text())[1])
            row.get_by_role('button',name='تعديل',exact=True).click()
        else:
            page.locator('#chat-memory-key').fill('communication.style')
        page.locator('#chat-memory-value').fill('I prefer concise answers with the practical solution first.')
        page.locator('#chat-memory-form button[type=submit]').click()
        expect(row).to_contain_text('v'+str(before_revision+1))
        row.get_by_role('button',name='تعديل',exact=True).click()
        page.locator('#chat-memory-value').fill('I prefer concise direct answers.')
        page.locator('#chat-memory-form button[type=submit]').click()
        expect(row).to_contain_text('v'+str(before_revision+2))
        row.get_by_role('button',name='المصدر والإصدارات',exact=True).click()
        expect(page.locator('#chat-memory-source-list')).to_contain_text('Superseded')
        expect(page.locator('#chat-memory-source-list')).to_contain_text('concise direct answers')
        report['checks']['memory_edit_correction_sources']=True
        page.locator('#chat-archive-query').fill('UI-841')
        page.locator('#chat-archive-scope').select_option('all')
        page.locator('#chat-archive-form button[type=submit]').click()
        expect(page.locator('#chat-archive-results')).to_contain_text('UI-841')
        page.locator('#chat-archive-results article').filter(has_text='My next task in this conversation').get_by_role('button').click()
        expect(page.locator('#chat-memory-manager')).not_to_have_attribute('open','')
        expect(page.locator('#chat-messages')).to_contain_text('UI-841')
        report['checks']['archive_search_and_source_resume']=True
        page.locator('#chat-memory-manager > summary').click()
        task=page.locator('#chat-memory-list article').filter(has_text='UI-841')
        expect(task).to_have_count(1)
        page.once('dialog',lambda dialog:dialog.accept())
        task.get_by_role('button',name='نسيان',exact=True).click()
        expect(task).to_have_count(0)
        page.locator('#chat-archive-query').fill('UI-841')
        page.locator('#chat-archive-form button[type=submit]').click()
        expect(page.locator('#chat-archive-results')).to_contain_text('No matching history')
        page.locator('#chat-memory-lifecycle').select_option('deleted')
        page.locator('#chat-memory-browse').click()
        expect(page.locator('#chat-memory-lifecycle-list')).to_contain_text('Deleted')
        report['checks']['forget_removes_sources_archive_and_active_memory']=True
        page.locator('#chat-retention').fill('0');page.locator('#chat-retention-save').click()
        expect(page.locator('#chat-retention')).to_have_value('0')
        report['checks']['indefinite_retention_control']=True
        report['page_errors']=errors;report['external_requests_denied']=external
        assert not errors and not external
        report['checks']['no_page_errors_or_external_requests']=True
        page.screenshot(path=str(args.output/'memory-after-forget.png'))
        context.close();browser.close()
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()

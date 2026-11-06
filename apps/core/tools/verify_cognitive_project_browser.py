#!/usr/bin/env python3
"""Real keyboard/mobile project paging against an owned isolated local process."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
from playwright.sync_api import sync_playwright, expect
from okal_core.intelligence import Intelligence
from okal_core.store import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    args=parser.parse_args()
    if not args.state.is_absolute() or args.state.exists() or 'okal-core' in args.state.parts:
        parser.error('fresh private synthetic state required')
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        probe.bind(('127.0.0.1',8880))
    os.umask(0o077);args.state.mkdir(parents=True,mode=0o700)
    chat=Intelligence(Store(args.state))
    chat.create('Synthetic keyboard fixture')
    old=chat.cognitive.save_project('Legacy continuity fixture','Long-running synthetic project.')
    for i in range(200):chat.cognitive.save_project('Recent project '+str(i))
    with chat.store.connect() as db,db:db.execute('UPDATE memory_projects SET updated_at=0 WHERE id=?',(old['id'],))
    source=Path(__file__).parents[1]/'src'
    with (args.state/'server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','okal_core','--state-dir',str(args.state),'serve','--port','8880'],
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(source.resolve()),'PYTHONDONTWRITEBYTECODE':'1'},
            stdout=log,stderr=log)
        try:
            with httpx.Client(trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get('http://127.0.0.1:8880/api/v1/health').status_code==200:break
                    except httpx.HTTPError:pass
                    if server.poll() is not None:raise RuntimeError('isolated_server_exited')
                    time.sleep(.1)
                else:raise RuntimeError('isolated_start_deadline')
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True)
                page=browser.new_page(viewport={'width':1365,'height':1000});errors=[];external=[]
                def local_only(route):
                    if not route.request.url.startswith('http://127.0.0.1:8880/'):
                        external.append(route.request.url);route.abort()
                    else:route.continue_()
                page.route('**/*',local_only);page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:8880/#chat-home')
                expect(page.locator('#chat-status')).to_contain_text('جاهزة',timeout=15000)
                summary=page.locator('#chat-memory-manager > summary');summary.focus();page.keyboard.press('Enter')
                expect(page.locator('#chat-memory-manager')).to_have_attribute('open','')
                expect(page.locator('#chat-project-more')).to_be_visible()
                assert page.locator('#chat-memory-project option').count()==201
                page.locator('#chat-project-more').focus();page.keyboard.press('Enter')
                expect(page.locator('#chat-project-more')).to_be_hidden()
                assert page.locator('#chat-memory-project option').count()==202
                page.get_by_label('المشروع / Project',exact=True).select_option(old['id'])
                expect(page.locator('#chat-memory-project')).to_have_value(old['id'])
                for width,height in [(390,844),(768,1024)]:
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert page.evaluate('innerWidth')==width
                page.set_viewport_size({'width':1365,'height':1000})
                page.get_by_label('كلمة أو موضوع',exact=True).focus()
                page.keyboard.type('Synthetic keyboard query')
                assert page.locator('#chat-archive-query').input_value()=='Synthetic keyboard query'
                assert page.locator('#chat-archive-query').evaluate('e=>getComputedStyle(e).outlineWidth')=='3px'
                page.locator('#chat-memory-project').scroll_into_view_if_needed()
                page.screenshot(path=str(args.state/'keyboard-project-paging.png'))
                assert not errors and not external
                report={'synthetic_only':True,'real_private_process_and_chromium':True,'projects':201,
                    'older_project_reachable_after_paging':True,'keyboard_disclosure_and_paging':True,
                    'labelled_input_keyboard_edit_and_visible_focus':True,'mobile_and_tablet_no_overflow':True,
                    'page_exceptions':errors,'external_requests':external}
                (args.state/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
                browser.close()
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait(timeout=10)


if __name__=='__main__':main()

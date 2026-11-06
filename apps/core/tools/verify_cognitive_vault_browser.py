#!/usr/bin/env python3
"""Real browser confirmation-race acceptance on the synthetic :8878 preview."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit
import uuid

from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if (not args.state.is_absolute() or 'okal-core' in args.state.parts
            or not (args.state/'core.sqlite3').is_file()
            or not args.output.is_absolute() or args.output.exists()):
        parser.error('existing isolated preview state and fresh output required')
    os.umask(0o077);args.output.mkdir(parents=True,mode=0o700)
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
        page.on('dialog',lambda dialog:dialog.accept())
        page.goto('http://127.0.0.1:8878/#chat-home')
        expect(page.locator('#chat-status')).to_contain_text('جاهزة',timeout=15000)
        def post(name,body):
            result=page.evaluate('''async ({name,body})=>{
                const response=await fetch('/api/v1/chat/'+name,{method:'POST',
                    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
                return {status:response.status,body:await response.json()};
            }''',{'name':name,'body':body})
            assert result['status']==200,(name,result['status'])
            return result['body']
        record=post('memory-save',{'key':'acceptance.preview.'+uuid.uuid4().hex[:8],
            'content':'I prefer reviewed offline notes.'})
        project=post('project-save',{'name':'Synthetic vault preview '+uuid.uuid4().hex[:8],
            'description':'Original synthetic project description.'})
        # Prove the running server points at the supplied synthetic state
        # before any filesystem edit. Production paths are never accepted.
        with sqlite3.connect((args.state/'core.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
            assert db.execute('SELECT content FROM chat_memories WHERE id=?',(record['id'],)).fetchone()[0]==record['content']
        post('memory-rebuild',{})
        vault=args.state/'cognitive/vault'
        memory_path=vault/'preferences'/('memory-'+record['id']+'.md')
        project_path=vault/'projects'/('project-'+project['id']+'.md')
        for _ in range(180):
            if memory_path.exists() and project_path.exists():break
            time.sleep(1)
        else:raise RuntimeError('projection_deadline')
        page.locator('#chat-memory-manager > summary').click()
        page.get_by_text('خزنة Obsidian المحلية / Knowledge vault',exact=True).click()
        page.locator('#chat-vault-memory').fill(record['id'])
        memory_path.write_text(memory_path.read_text().replace(record['content'],'I prefer previewed offline notes.'))
        page.locator('#chat-vault-preview').click()
        expect(page.locator('#chat-vault-preview-text')).to_have_text('I prefer previewed offline notes.')
        memory_path.write_text(memory_path.read_text().replace('previewed offline','subsequently edited offline'))
        with page.expect_response(lambda r:r.url.endswith('/vault-import')) as response:
            page.locator('#chat-vault-import').click()
        assert response.value.status==409
        current=next(r for r in post('memories',{})['items'] if r['id']==record['id'])
        assert current['revision']==1 and current['content']==record['content']
        page.locator('#chat-vault-preview').click()
        expect(page.locator('#chat-vault-preview-text')).to_have_text('I prefer subsequently edited offline notes.')
        with page.expect_response(lambda r:r.url.endswith('/vault-import')) as response:
            page.locator('#chat-vault-import').click()
        assert response.value.status==200
        current=next(r for r in post('memories',{})['items'] if r['id']==record['id'])
        assert current['revision']==2 and current['content']=='I prefer subsequently edited offline notes.'
        page.locator('#chat-memory-project').select_option(project['id'])
        project_path.write_text(project_path.read_text().replace(project['description'],'Previewed synthetic description.'))
        page.locator('#chat-vault-project-preview').click()
        expect(page.locator('#chat-vault-project-text')).to_have_text('Previewed synthetic description.')
        project_path.write_text(project_path.read_text().replace('Previewed synthetic','Unseen synthetic'))
        with page.expect_response(lambda r:r.url.endswith('/vault-project-import')) as response:
            page.locator('#chat-vault-project-import').click()
        assert response.value.status==409
        current=next(r for r in post('projects',{})['items'] if r['id']==project['id'])
        assert current['revision']==1 and current['description']==project['description']
        page.locator('#chat-vault-project-preview').click()
        expect(page.locator('#chat-vault-project-text')).to_have_text('Unseen synthetic description.')
        with page.expect_response(lambda r:r.url.endswith('/vault-project-import')) as response:
            page.locator('#chat-vault-project-import').click()
        assert response.value.status==200
        current=next(r for r in post('projects',{})['items'] if r['id']==project['id'])
        assert current['revision']==2 and current['description']=='Unseen synthetic description.'
        page.locator('#chat-vault-project-preview').click()
        expect(page.locator('#chat-vault-project-text')).to_have_text(current['description'])
        page.screenshot(path=str(args.output/'confirmed-vault-preview.png'))
        report={'synthetic_only':True,'real_chromium':True,
            'memory_changed_after_preview_rejected_409':True,'project_changed_after_preview_rejected_409':True,
            'ledger_unchanged_on_rejection':True,'fresh_previews_imported_revision_2':True,
            'page_exceptions':errors,'external_requests':external}
        assert not errors and not external
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
        browser.close()


if __name__=='__main__':main()

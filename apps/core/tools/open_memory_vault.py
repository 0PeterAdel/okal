#!/usr/bin/env python3
"""Open the curated vault with a private offline Obsidian desktop profile.

Optional owner-operated launcher, never a computer-action tool. Requires the
reviewed Arch Obsidian/Electron package and unprivileged bubblewrap namespaces.
No network, D-Bus, credential, home-directory or authoritative database mounts.
"""
import argparse
import json
import os
from pathlib import Path
import stat

from okal_core.mail.private import write_private
from okal_core.store import private_directory

CORE_PLUGINS={'file-explorer','switcher','backlink','outgoing-link','graph','outline','properties','canvas','bookmarks','bases'}


def build_command(state: Path) -> list[str]:
    if not state.is_absolute():raise ValueError('absolute_private_state_required')
    cognitive=private_directory(state/'cognitive')
    vault=cognitive/'vault'
    if not vault.is_dir():raise ValueError('curated_vault_not_created_yet')
    private_directory(vault)
    config=private_directory(vault/'.obsidian')
    for name,default in [('core-plugins.json',sorted(CORE_PLUGINS)),('community-plugins.json',[])]:
        path=config/name
        if not path.exists():write_private(path,default)
        info=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_size>16_000):
            raise ValueError('invalid_private_obsidian_settings')
        value=json.loads(path.read_text())
        if name=='core-plugins.json' and isinstance(value,dict):
            if any(type(k) is not str or type(v) is not bool for k,v in value.items()):
                raise ValueError('invalid_obsidian_plugin_map')
            value=[k for k,v in value.items() if v]
        if not isinstance(value,list) or any(type(v) is not str for v in value):
            raise ValueError('invalid_obsidian_plugin_list')
        if (name=='core-plugins.json' and not set(value)<=CORE_PLUGINS
                or name=='community-plugins.json' and value):
            raise ValueError('offline_vault_requires_reviewed_plugins_no_sync_or_file_recovery')
    app=config/'app.json'
    if not app.exists():write_private(app,{'showInlineTitle':False})
    profile=private_directory(cognitive/'obsidian-profile')
    # This separate profile has no personal Obsidian accounts or vault registry.
    write_private(profile/'obsidian.json',{'updateDisabled':True,
        'vaults':{'0a1b2c3d4e5f6789':{'path':'/vault','ts':0,'open':True}}})
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR',''))
    display=os.environ.get('WAYLAND_DISPLAY','')
    if not runtime.is_absolute() or not display or Path(display).name!=display:
        raise ValueError('local_wayland_session_required')
    socket=runtime/display
    if not socket.is_socket() or socket.stat().st_uid!=os.getuid():
        raise ValueError('owner_wayland_socket_required')
    if not Path('/usr/bin/bwrap').is_file() or not Path('/usr/bin/electron43').is_file() or not Path('/usr/lib/obsidian/app.asar').is_file():
        raise ValueError('reviewed_obsidian_electron43_and_bubblewrap_required')
    command=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session',
        '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib',
        '--symlink','usr/lib','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp',
        '--dir','/etc','--ro-bind','/etc/fonts','/etc/fonts','--ro-bind','/etc/ld.so.cache','/etc/ld.so.cache',
        '--dir',str(runtime),'--ro-bind',str(socket),str(socket),
        '--bind',str(profile),'/profile','--bind',str(vault),'/vault',
        '--setenv','XDG_CONFIG_HOME','/profile/config','--setenv','XDG_CACHE_HOME','/profile/cache',
        '--setenv','XDG_DATA_HOME','/profile/data','--setenv','XDG_RUNTIME_DIR',str(runtime),
        '--setenv','WAYLAND_DISPLAY',display,'--unsetenv','DISPLAY','--unsetenv','DBUS_SESSION_BUS_ADDRESS',
        '/usr/bin/electron43','/usr/lib/obsidian/app.asar','--user-data-dir=/profile',
        '--ozone-platform=wayland','--disable-gpu','--no-sandbox']
    # Chromium's inner sandbox is disabled because the enclosing unprivileged
    # OS namespace supplies the filesystem/network boundary. The Wayland socket
    # still permits normal compositor interaction; this is not a hostile-GUI VM.
    return command


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,required=True)
    args=parser.parse_args()
    os.umask(0o077)
    command=build_command(args.state_dir)
    # No inherited cloud credentials, proxies, mail settings or session bus.
    clean={k:os.environ[k] for k in ('PATH','LANG','LC_ALL') if k in os.environ}
    os.execvpe(command[0],command,clean)


if __name__=='__main__':main()

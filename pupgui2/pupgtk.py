import os
import threading
import shutil
import re
import requests

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio, GObject

from pupgui2 import ctloader
from pupgui2.constants import APP_ID, APP_VERSION, TEMP_DIR
from pupgui2.constants import PROTONDB_API_URL
from pupgui2.constants import HOME_DIR
from pupgui2.datastructures import RuntimeType
from pupgui2.heroicutil import get_heroic_game_list, is_heroic_launcher
from pupgui2.lutrisutil import get_lutris_game_list
from pupgui2.steamutil import remove_steamtinkerlaunch
from pupgui2.steamutil import get_steam_game_list
from pupgui2.steamutil import steam_update_ctools
from pupgui2.util import (
    available_install_directories,
    config_advanced_mode,
    config_custom_install_location,
    config_github_access_token,
    config_gitlab_access_token,
    create_compatibilitytools_folder,
    get_install_location_from_directory_name,
    get_installed_ctools,
    install_directory,
)


class AboutDialog(Gtk.Window):
    def __init__(self, parent):
        super().__init__(title='About ProtonUp-GTK')
        self.set_application(parent.get_application())
        self.set_default_size(520, 340)
        self.parent = parent

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self.set_child(scrolled)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)
        scrolled.set_child(root)

        root.append(Gtk.Label(label='ProtonUp-GTK v1.00 by stf_ftw', xalign=0))
        root.append(Gtk.Label(label='Based on ProtonUp-Qt v2.15.0 by DavidoTek', xalign=0))

        self.gh_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.gh_row.append(Gtk.Label(label='GitHub Access Token', xalign=0))
        self.github_entry = Gtk.Entry()
        self.github_entry.set_text(config_github_access_token())
        self.gh_row.append(self.github_entry)
        root.append(self.gh_row)

        self.gl_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.gl_row.append(Gtk.Label(label='GitLab Access Token', xalign=0))
        self.gitlab_entry = Gtk.Entry()
        self.gitlab_entry.set_text(config_gitlab_access_token())
        self.gl_row.append(self.gitlab_entry)
        root.append(self.gl_row)

        adv_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        adv_row.append(Gtk.Label(label='Advanced mode', xalign=0))
        self.advanced_switch = Gtk.Switch()
        self.advanced_switch.set_active('true' in config_advanced_mode().lower())
        adv_row.append(self.advanced_switch)
        root.append(adv_row)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.set_halign(Gtk.Align.END)
        self.save_btn = Gtk.Button(label='Save')
        self.close_btn = Gtk.Button(label='Close')
        action_row.append(self.close_btn)
        action_row.append(self.save_btn)
        root.append(action_row)

        self.close_btn.connect('clicked', lambda *_: self.close())
        self.save_btn.connect('clicked', self._on_save_clicked)
        self.advanced_switch.connect('notify::active', self._on_advanced_toggled)
        self._set_advanced_widgets_visible(self.advanced_switch.get_active())

    def _set_advanced_widgets_visible(self, is_visible: bool):
        self.gh_row.set_visible(is_visible)
        self.gl_row.set_visible(is_visible)
        self.close_btn.set_visible(is_visible)
        self.save_btn.set_visible(is_visible)

    def _on_advanced_toggled(self, *_):
        self._set_advanced_widgets_visible(self.advanced_switch.get_active())

    def _on_save_clicked(self, *_):
        config_advanced_mode('true' if self.advanced_switch.get_active() else 'false')
        config_github_access_token(self.github_entry.get_text().strip())
        config_gitlab_access_token(self.gitlab_entry.get_text().strip())
        self.parent.refresh_installed_versions()
        self.close()


class CustomInstallDirectoryWindow(Gtk.Window):
    INSTALL_LOCATIONS = {
        'steam': 'Steam',
        'lutris': 'Lutris',
        'heroicwine': 'Heroic (Wine)',
        'heroicproton': 'Heroic (Proton)',
        'bottles': 'Bottles',
        'winezgui': 'WineZGUI',
    }

    def __init__(self, parent):
        super().__init__(title='Custom Install Directory')
        self.parent = parent
        self.set_application(parent.get_application())
        self.set_default_size(760, 380)

        self.launcher_keys = list(self.INSTALL_LOCATIONS.keys())

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)
        self.set_child(root)

        desc = Gtk.Label(
            label="Specify a custom location for downloading and displaying a launcher's compatibility tools.",
            xalign=0,
            wrap=True,
        )
        root.append(desc)

        dir_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        dir_row.append(Gtk.Label(label='Directory:', xalign=0))
        self.dir_entry = Gtk.Entry()
        self.dir_entry.set_hexpand(True)
        dir_row.append(self.dir_entry)
        self.browse_btn = Gtk.Button(label='Browse')
        dir_row.append(self.browse_btn)
        root.append(dir_row)

        launch_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        launch_row.append(Gtk.Label(label='Launcher:', xalign=0))
        self.launcher_dropdown = Gtk.DropDown(model=Gtk.StringList.new(list(self.INSTALL_LOCATIONS.values())))
        self.launcher_dropdown.set_hexpand(True)
        launch_row.append(self.launcher_dropdown)
        root.append(launch_row)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.set_halign(Gtk.Align.END)
        self.default_btn = Gtk.Button(label='Default')
        self.save_btn = Gtk.Button(label='Save')
        close_btn = Gtk.Button(label='Close')
        action_row.append(self.default_btn)
        action_row.append(self.save_btn)
        action_row.append(close_btn)
        root.append(action_row)

        self.dir_entry.connect('changed', self._on_path_changed)
        self.browse_btn.connect('clicked', self._on_browse_clicked)
        self.default_btn.connect('clicked', self._on_default_clicked)
        self.save_btn.connect('clicked', self._on_save_clicked)
        close_btn.connect('clicked', lambda *_: self.close())

        self._load_initial_state()

    def _load_initial_state(self):
        current_install = get_install_location_from_directory_name(install_directory())
        current_launcher = current_install.get('launcher', 'steam')

        custom = config_custom_install_location()
        custom_dir = custom.get('install_dir', '') or ''
        custom_launcher = custom.get('launcher', '') or current_launcher

        self.dir_entry.set_text(custom_dir)
        self.default_btn.set_sensitive(bool(custom_dir))

        if custom_launcher in self.launcher_keys:
            self.launcher_dropdown.set_selected(self.launcher_keys.index(custom_launcher))
        else:
            self.launcher_dropdown.set_selected(0)

        self.save_btn.set_sensitive(self._is_valid_custom_install_path(custom_dir))

    def _on_path_changed(self, *_):
        path = self.dir_entry.get_text().strip()
        self.save_btn.set_sensitive(self._is_valid_custom_install_path(path))

    def _on_browse_clicked(self, *_):
        current = os.path.expanduser(self.dir_entry.get_text().strip())
        initial = current if self._is_valid_custom_install_path(current) else HOME_DIR

        chooser = Gtk.FileChooserNative.new(
            'Select Custom Install Directory - ProtonUp-GTK',
            self,
            Gtk.FileChooserAction.SELECT_FOLDER,
            'Select',
            'Cancel',
        )
        chooser.set_current_folder(Gio.File.new_for_path(os.path.expanduser(initial)))
        chooser.connect('response', self._on_browse_response)
        chooser.show()

    def _on_browse_response(self, chooser, response):
        try:
            if response == Gtk.ResponseType.ACCEPT:
                file = chooser.get_file()
                if file is not None:
                    path = file.get_path()
                    if path:
                        self.dir_entry.set_text(path)
        finally:
            chooser.destroy()

    def _on_default_clicked(self, *_):
        self.dir_entry.set_text('')
        config_custom_install_location(remove=True)
        install_directory('default')
        self.parent.refresh_install_locations()
        self.parent.refresh_installed_versions()
        self.default_btn.set_sensitive(False)

    def _on_save_clicked(self, *_):
        install_dir_path = os.path.expanduser(self.dir_entry.get_text().strip())
        if not install_dir_path.endswith(os.sep):
            install_dir_path += os.sep

        if not self._is_valid_custom_install_path(install_dir_path):
            self.parent.show_message('Invalid Directory', 'Please select a valid writable directory.')
            return

        launcher_idx = self.launcher_dropdown.get_selected()
        launcher = self.launcher_keys[launcher_idx] if launcher_idx < len(self.launcher_keys) else 'steam'

        config_custom_install_location(install_dir_path, launcher)
        install_directory(install_dir_path)
        self.parent.refresh_install_locations()
        self.parent.refresh_installed_versions()
        self.close()

    def _is_valid_custom_install_path(self, path: str) -> bool:
        expand_path = os.path.expanduser(path.strip())
        return len(expand_path) > 0 and os.path.isdir(expand_path) and os.access(expand_path, os.W_OK)


class GameListRow(GObject.Object):
    game = GObject.Property(type=str, default='')
    compat = GObject.Property(type=str, default='')
    compat_internal = GObject.Property(type=str, default='')
    deck = GObject.Property(type=str, default='')
    anticheat = GObject.Property(type=str, default='')
    protondb = GObject.Property(type=str, default='')
    app_id = GObject.Property(type=int, default=0)

    def __init__(self, game='', compat='', compat_internal='', deck='', anticheat='', protondb='', app_id=0):
        super().__init__()
        self.game = game
        self.compat = compat
        self.compat_internal = compat_internal
        self.deck = deck
        self.anticheat = anticheat
        self.protondb = protondb
        self.app_id = app_id


class GameListDialog(Gtk.Window):
    def __init__(self, parent, install_loc: dict):
        launcher_name = install_loc.get('display_name') or 'Unknown'
        super().__init__(title=f'Game List for {launcher_name}')
        self.set_application(parent.get_application())
        self.set_default_size(1150, 620)
        self.parent = parent
        self.install_loc = install_loc
        self._all_rows: list[GameListRow] = []
        self._protondb_cache: dict[int, str] = {}
        self._steam_games_by_appid = {}
        self._steam_original_compat = {}
        self._steam_pending_compat = {}
        self._steam_compat_options: list[tuple[str, str | None]] = [('Default', None)]

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)
        self.set_child(root)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text('Search games...')
        self.search_entry.connect('search-changed', self._on_search_changed)
        root.append(self.search_entry)

        self.store = Gio.ListStore.new(GameListRow)
        self.selection = Gtk.SingleSelection.new(self.store)
        self.column_view = Gtk.ColumnView.new(self.selection)
        self.column_view.set_hexpand(True)
        self.column_view.set_vexpand(True)

        self._append_text_column('Game', 'game')
        self._append_compat_column()
        self._append_text_column('Deck Compatibility', 'deck')
        self._append_text_column('Anticheat', 'anticheat')
        self._append_protondb_column()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        scrolled.set_child(self.column_view)
        root.append(scrolled)

        if self.install_loc.get('launcher') == 'steam':
            warning = Gtk.Label(
                label='Warning: Close the Steam client beforehand so that changes can be applied.',
                xalign=0,
            )
            warning.add_css_class('dim-label')
            root.append(warning)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        refresh_btn = Gtk.Button(label='Refresh')
        self.apply_close_btn = Gtk.Button(label='Close')
        refresh_btn.connect('clicked', lambda *_: self.reload())
        self.apply_close_btn.connect('clicked', self._on_apply_or_close_clicked)
        actions.append(refresh_btn)
        actions.append(self.apply_close_btn)
        root.append(actions)

        self.reload()

    def _append_text_column(self, title: str, attr: str):
        factory = Gtk.SignalListItemFactory()

        def on_setup(_factory, list_item):
            if title == 'Game':
                label = Gtk.Label(xalign=0)
                label.set_ellipsize(0)  # Pango.EllipsizeMode.NONE
                label.set_single_line_mode(True)
                scroller = Gtk.ScrolledWindow()
                scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
                scroller.set_child(label)
                list_item.set_child(scroller)
                list_item._text_label = label
            else:
                label = Gtk.Label(xalign=0)
                label.set_ellipsize(3)  # Pango.EllipsizeMode.END
                list_item.set_child(label)
                list_item._text_label = label

        def on_bind(_factory, list_item):
            item = list_item.get_item()
            label = getattr(list_item, '_text_label', None)
            if label is None:
                return
            label.set_text(getattr(item, attr, ''))

        factory.connect('setup', on_setup)
        factory.connect('bind', on_bind)
        col = Gtk.ColumnViewColumn.new(title, factory)
        col.set_resizable(True)
        if title == 'Game':
            col.set_expand(True)
        elif title == 'Deck Compatibility':
            col.set_fixed_width(260)
        elif title == 'Anticheat':
            col.set_fixed_width(140)
        self.column_view.append_column(col)

    def _append_compat_column(self):
        factory = Gtk.SignalListItemFactory()

        def on_setup(_factory, list_item):
            dropdown = Gtk.DropDown()
            dropdown.set_size_request(260, -1)
            dropdown.connect('notify::selected-item', self._on_compat_dropdown_changed)
            list_item.set_child(dropdown)

        def on_bind(_factory, list_item):
            row = list_item.get_item()
            dropdown = list_item.get_child()
            dropdown._bound_row = row
            self._bind_compat_dropdown(dropdown, row)

        factory.connect('setup', on_setup)
        factory.connect('bind', on_bind)
        col = Gtk.ColumnViewColumn.new('Compatibility Tool', factory)
        col.set_resizable(True)
        col.set_fixed_width(280)
        self.column_view.append_column(col)

    def _bind_compat_dropdown(self, dropdown: Gtk.DropDown, row: GameListRow):
        dropdown._binding = True
        labels = [label for (label, _internal) in self._steam_compat_options]
        model = Gtk.StringList.new(labels)
        dropdown.set_model(model)

        if self.install_loc.get('launcher') != 'steam' or row.app_id <= 0:
            # Non-Steam: show single static value
            static_model = Gtk.StringList.new([row.compat or '-'])
            dropdown.set_model(static_model)
            dropdown.set_selected(0)
            dropdown.set_sensitive(False)
            GLib.idle_add(self._clear_dropdown_binding, dropdown)
            return

        dropdown.set_sensitive(True)
        current_internal = row.compat_internal if row.compat_internal else None
        selected_idx = 0
        for i, (_label, internal) in enumerate(self._steam_compat_options):
            if internal == current_internal:
                selected_idx = i
                break
        dropdown.set_selected(selected_idx)
        GLib.idle_add(self._clear_dropdown_binding, dropdown)

    def _clear_dropdown_binding(self, dropdown: Gtk.DropDown):
        dropdown._binding = False
        return False

    def _on_compat_dropdown_changed(self, dropdown, *_):
        if getattr(dropdown, '_binding', False):
            return

        row = getattr(dropdown, '_bound_row', None)
        if row is None or row.app_id <= 0:
            return

        selected = dropdown.get_selected()
        if selected == Gtk.INVALID_LIST_POSITION:
            return

        if selected >= len(self._steam_compat_options):
            return

        label, internal = self._steam_compat_options[selected]
        row.compat = label
        row.compat_internal = internal or ''

        app_id = int(row.app_id)
        original_internal = self._steam_original_compat.get(app_id, None)
        if original_internal == internal:
            self._steam_pending_compat.pop(app_id, None)
        else:
            self._steam_pending_compat[app_id] = internal

        self._update_apply_close_button()

    def _update_apply_close_button(self):
        self.apply_close_btn.set_label('Apply' if len(self._steam_pending_compat) > 0 else 'Close')

    def _on_apply_or_close_clicked(self, *_):
        if len(self._steam_pending_compat) <= 0:
            self.close()
            return

        changes = {}
        for app_id, compat_internal in self._steam_pending_compat.items():
            game_obj = self._steam_games_by_appid.get(app_id)
            if game_obj is not None:
                changes[game_obj] = compat_internal

        if changes:
            steam_update_ctools(changes, steam_config_folder=self.install_loc.get('vdf_dir'))

        self._steam_pending_compat = {}
        self.reload()
        self._update_apply_close_button()

    def _append_protondb_column(self):
        factory = Gtk.SignalListItemFactory()

        def on_setup(_factory, list_item):
            btn = Gtk.Button(label='-')
            btn.set_size_request(150, -1)
            btn.connect('clicked', self._on_protondb_button_clicked, list_item)
            list_item.set_child(btn)

        def on_bind(_factory, list_item):
            row = list_item.get_item()
            btn = list_item.get_child()
            self._update_protondb_button(btn, row)

        factory.connect('setup', on_setup)
        factory.connect('bind', on_bind)
        col = Gtk.ColumnViewColumn.new('ProtonDB', factory)
        col.set_resizable(True)
        col.set_fixed_width(170)
        self.column_view.append_column(col)

    def _update_protondb_button(self, button: Gtk.Button, row: GameListRow):
        if row.app_id <= 0:
            button.set_label('-')
            button.set_sensitive(False)
            return

        label = row.protondb or 'Press for info'
        button.set_label(label)
        # Only allow clicks while waiting for first fetch.
        # After showing any result (including "Unknown"), keep it as read-only.
        button.set_sensitive(label == 'Press for info')

    def _on_protondb_button_clicked(self, button: Gtk.Button, list_item):
        row = list_item.get_item()
        if row is None or row.app_id <= 0:
            return

        # Keep behavior simple: if we already have data (not placeholder/loading), skip.
        if row.protondb not in ('', 'Press for info', 'Unknown', 'Loading...'):
            return
        if row.protondb == 'Loading...':
            return

        self._protondb_cache[int(row.app_id)] = 'Loading...'
        self.reload()

        t = threading.Thread(target=self._fetch_protondb_thread, args=(int(row.app_id),), daemon=True)
        t.start()

    def _fetch_protondb_thread(self, app_id: int):
        tier_text = 'Unknown'
        try:
            r = requests.get(PROTONDB_API_URL.format(game_id=str(app_id)), timeout=10)
            if r.status_code == 200:
                tier = r.json().get('tier', '')
                if tier:
                    tier_text = str(tier).capitalize()
        except Exception:
            pass

        GLib.idle_add(self._set_protondb_result, app_id, tier_text)

    def _set_protondb_result(self, app_id: int, tier_text: str):
        self._protondb_cache[int(app_id)] = tier_text
        self.reload()
        return False

    def _on_search_changed(self, *_):
        query = self.search_entry.get_text().strip().lower()
        self._rebuild_store(query=query)

    def _rebuild_store(self, query: str = ''):
        self.store.remove_all()
        for row in self._all_rows:
            if query and query not in row.game.lower():
                continue
            self.store.append(row)

    def reload(self):
        self._build_steam_compat_options()
        self._all_rows = self._build_rows()
        self._rebuild_store(query=self.search_entry.get_text().strip().lower())
        self._update_apply_close_button()

    def _build_steam_compat_options(self):
        self._steam_compat_options = [('Default', None)]
        if self.install_loc.get('launcher') != 'steam':
            return

        install_dir = self.install_loc.get('install_dir', '')
        for ct in get_installed_ctools(os.path.expanduser(install_dir)):
            internal = ct.get_internal_name()
            display = ct.get_displayname()
            self._steam_compat_options.append((display, internal))

    def _ensure_steam_compat_option(self, internal: str | None):
        if not internal:
            return
        if any(existing_internal == internal for _, existing_internal in self._steam_compat_options):
            return
        # Fallback label for tools that are valid in Steam config but not discovered from install dir list.
        self._steam_compat_options.append((internal, internal))

    def _compat_label_from_internal(self, internal: str | None) -> str:
        if not internal:
            return 'Default'
        for label, opt_internal in self._steam_compat_options:
            if opt_internal == internal:
                return label
        return internal

    def _build_rows(self) -> list[GameListRow]:
        launcher = self.install_loc.get('launcher', '')
        rows: list[GameListRow] = []

        if launcher == 'steam' and 'vdf_dir' in self.install_loc:
            games = get_steam_game_list(self.install_loc.get('vdf_dir'), cached=False)
            self._steam_games_by_appid = {}
            for game in games:
                app_id = int(game.app_id)
                self._steam_games_by_appid[app_id] = game

                deck = self._steam_deck_text(game)
                anticheat = self._steam_anticheat_text(game)
                protondb = str(game.protondb_summary.get('tier', '') or '').capitalize() or 'Unknown'

                if app_id not in self._protondb_cache:
                    self._protondb_cache[app_id] = 'Press for info' if protondb == 'Unknown' else protondb

                original_internal = game.compat_tool if game.compat_tool else None
                self._steam_original_compat[app_id] = original_internal
                effective_internal = self._steam_pending_compat.get(app_id, original_internal)
                self._ensure_steam_compat_option(original_internal)
                self._ensure_steam_compat_option(effective_internal)

                compat_display = self._compat_label_from_internal(effective_internal)

                rows.append(
                    GameListRow(
                        game=game.game_name or f'App {app_id}',
                        compat=compat_display,
                        compat_internal=effective_internal or '',
                        deck=deck,
                        anticheat=anticheat,
                        protondb=self._protondb_cache.get(app_id, 'Press for info'),
                        app_id=app_id,
                    )
                )
        elif launcher == 'lutris':
            games = get_lutris_game_list(self.install_loc)
            for game in games:
                rows.append(
                    GameListRow(
                        game=game.name or game.slug,
                        compat=game.runner or 'Unknown',
                        deck='-',
                        anticheat='-',
                        protondb='-',
                    )
                )
        elif is_heroic_launcher(launcher):
            heroic_dir = os.path.join(os.path.expanduser(self.install_loc.get('install_dir')), '../..')
            games = [g for g in get_heroic_game_list(heroic_dir) if g.is_installed and not g.is_dlc]
            for game in games:
                rows.append(
                    GameListRow(
                        game=game.title,
                        compat=game.wine_info.get('name', '') or game.runner or 'Unknown',
                        deck='-',
                        anticheat='-',
                        protondb='-',
                    )
                )

        rows.sort(key=lambda r: r.game.lower())
        return rows

    def _steam_deck_text(self, game) -> str:
        category = game.get_deck_compat_category().name
        mapping = {
            'VERIFIED': 'Verified',
            'PLAYABLE': 'Playable',
            'UNSUPPORTED': 'Unsupported',
            'UNKNOWN': 'Unknown',
        }
        label = mapping.get(category, 'Unknown')
        recommended = game.get_deck_recommended_tool()
        if recommended:
            return f'{label} using {recommended}'
        return label

    def _steam_anticheat_text(self, game) -> str:
        eac = bool(game.anticheat_runtimes.get(RuntimeType.EAC, False))
        battleye = bool(game.anticheat_runtimes.get(RuntimeType.BATTLEYE, False))
        if eac and battleye:
            return 'EAC + BattlEye'
        if eac:
            return 'EAC'
        if battleye:
            return 'BattlEye'
        return '-'


class InstallDialog(Gtk.Window):
    def __init__(self, parent, install_dir: str):
        super().__init__(title='Install Compatibility Tool')
        self.set_application(parent.get_application())
        self.set_default_size(560, 220)

        self.parent = parent
        self.install_dir = install_dir
        self.ctobjs = self.parent.get_ctobjs_for_install_dir(install_dir)
        self._version_values = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)
        self.set_child(root)

        tool_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        tool_row.append(Gtk.Label(label='Tool', xalign=0))
        self.tool_model = Gtk.StringList.new([ctobj['name'] for ctobj in self.ctobjs])
        self.tool_dropdown = Gtk.DropDown(model=self.tool_model)
        self.tool_dropdown.set_hexpand(True)
        tool_row.append(self.tool_dropdown)
        root.append(tool_row)

        ver_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ver_row.append(Gtk.Label(label='Version', xalign=0))
        self.version_model = Gtk.StringList.new([])
        self.version_dropdown = Gtk.DropDown(model=self.version_model)
        self.version_dropdown.set_hexpand(True)
        ver_row.append(self.version_dropdown)
        root.append(ver_row)

        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_visible(False)
        root.append(self.progress)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.set_halign(Gtk.Align.END)
        self.load_versions_btn = Gtk.Button(label='Load Versions')
        self.install_btn = Gtk.Button(label='Install')
        self.cancel_btn = Gtk.Button(label='Cancel')
        self.install_btn.set_sensitive(False)

        action_row.append(self.cancel_btn)
        action_row.append(self.load_versions_btn)
        action_row.append(self.install_btn)
        root.append(action_row)

        self.tool_dropdown.connect('notify::selected', self._on_tool_changed)
        self.load_versions_btn.connect('clicked', self._on_load_versions_clicked)
        self.install_btn.connect('clicked', self._on_install_clicked)
        self.cancel_btn.connect('clicked', lambda *_: self.close())

        if len(self.ctobjs) > 0:
            self.tool_dropdown.set_selected(0)
            self._load_versions()

    def _on_tool_changed(self, *_):
        self._load_versions()

    def _on_load_versions_clicked(self, *_):
        self._load_versions()

    def _load_versions(self):
        self.install_btn.set_sensitive(False)
        self.progress.set_visible(True)
        self.progress.set_text('Fetching versions...')
        self.progress.pulse()

        thread = threading.Thread(target=self._load_versions_thread, daemon=True)
        thread.start()

    def _load_versions_thread(self):
        ctobj = self.get_selected_ctobj()
        versions = []
        if ctobj is not None:
            try:
                versions = ctobj['installer'].fetch_releases()
            except Exception as e:
                GLib.idle_add(self.parent.show_message, 'Error', f'Failed to fetch versions: {e}')

        versions = sorted(list(dict.fromkeys(versions)), key=self._version_sort_key, reverse=True)
        GLib.idle_add(self._set_versions, versions)

    @staticmethod
    def _version_sort_key(tag: str):
        parts = re.findall(r'\d+|\D+', tag)
        key = []
        for part in parts:
            if part.isdigit():
                key.append((0, int(part)))
            else:
                key.append((1, part.lower()))
        return key

    def _set_versions(self, versions: list[str]):
        self._version_values = versions
        self.version_model = Gtk.StringList.new(versions)
        self.version_dropdown.set_model(self.version_model)
        self.version_dropdown.set_selected(0 if versions else Gtk.INVALID_LIST_POSITION)
        self.install_btn.set_sensitive(bool(versions))
        self.progress.set_visible(False)
        return False

    def _on_install_clicked(self, *_):
        ctobj = self.get_selected_ctobj()
        if ctobj is None:
            return

        idx = self.version_dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self._version_values):
            self.parent.show_message('Error', 'Please select a version to install.')
            return

        version = self._version_values[idx]
        self.parent.install_tool(ctobj, version, self.install_dir)
        self.close()

    def get_selected_ctobj(self):
        idx = self.tool_dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self.ctobjs):
            return None
        return self.ctobjs[idx]


class MainWindow(Adw.ApplicationWindow):
    APP_DISPLAY_NAME = 'ProtonUp-GTK'
    APP_DISPLAY_VERSION = '1.0.0'

    def __init__(self, app):
        super().__init__(application=app, title=self.APP_DISPLAY_NAME, default_width=820, default_height=560)

        self.web_access_tokens = {
            'github': os.getenv('PUPGUI_GHA_TOKEN') or config_github_access_token(),
            'gitlab': os.getenv('PUPGUI_GLA_TOKEN') or config_gitlab_access_token(),
        }

        self.ct_loader = ctloader.CtLoader(main_window=self)
        self.ct_loader.load_ctmods()
        self._connect_installer_signals()

        self._install_paths = []
        self._display_index_map = []
        self._list_index_map = []

        self._build_ui()
        create_compatibilitytools_folder()
        self.refresh_install_locations()
        self.refresh_installed_versions()

    def _build_ui(self):
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=self.APP_DISPLAY_NAME, subtitle=f'v{self.APP_DISPLAY_VERSION}'))

        self.btn_about = Gtk.Button(label='About')
        self.btn_custom_install = Gtk.Button(label='...')
        self.btn_custom_install.set_tooltip_text('Add Custom Install Directory')
        self.btn_add = Gtk.Button(label='Add Version')
        self.btn_show_info = Gtk.Button(label='Show Info')
        self.btn_show_game_list = Gtk.Button(label='Show Game List')
        self.btn_remove = Gtk.Button(label='Remove Selected')

        header.pack_start(self.btn_about)

        self.btn_about.connect('clicked', self._on_about_clicked)
        self.btn_custom_install.connect('clicked', self._on_custom_install_clicked)
        self.btn_add.connect('clicked', self._on_add_clicked)
        self.btn_show_info.connect('clicked', self._on_show_info_clicked)
        self.btn_show_game_list.connect('clicked', self._on_show_game_list_clicked)
        self.btn_remove.connect('clicked', self._on_remove_clicked)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        install_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_row.append(Gtk.Label(label='Install Location', xalign=0))
        self.install_icon = Gtk.Image(icon_name='folder-symbolic')
        self.install_icon.set_pixel_size(20)
        install_row.append(self.install_icon)
        self.install_dropdown = Gtk.DropDown()
        self.install_dropdown.set_hexpand(True)
        self.install_dropdown.connect('notify::selected', self._on_install_location_changed)
        install_row.append(self.install_dropdown)
        install_row.append(self.btn_custom_install)
        content.append(install_row)

        self.summary = Gtk.Label(label='', xalign=0)
        content.append(self.summary)

        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_visible(False)
        content.append(self.progress)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect('row-selected', self._on_row_selected)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        scrolled.set_child(self.listbox)
        content.append(scrolled)

        bottom_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom_actions.set_halign(Gtk.Align.END)
        bottom_actions.append(self.btn_show_game_list)
        bottom_actions.append(self.btn_show_info)
        bottom_actions.append(self.btn_add)
        bottom_actions.append(self.btn_remove)
        content.append(bottom_actions)

        container = Adw.ToolbarView()
        container.add_top_bar(header)
        container.set_content(content)
        self.set_content(container)

    def _connect_installer_signals(self):
        for ctobj in self.ct_loader.get_ctobjs():
            cti = ctobj['installer']
            if hasattr(cti, 'download_progress_percent'):
                cti.download_progress_percent.connect(self._on_download_progress)
            if hasattr(cti, 'message_box_message'):
                cti.message_box_message.connect(self._on_installer_message)

    def _on_download_progress(self, value: int):
        GLib.idle_add(self._set_progress_value, value)

    def _set_progress_value(self, value: int):
        if value < 0:
            self.progress.set_visible(False)
            self.progress.set_fraction(0.0)
            self.progress.set_text('')
            return False

        self.progress.set_visible(True)
        if value >= 100:
            self.progress.set_fraction(1.0)
            self.progress.set_text('Done')
        else:
            self.progress.set_fraction(max(0.0, min(1.0, float(value) / 100.0)))
            self.progress.set_text(f'{value}%')
        return False

    def _on_installer_message(self, title, text, _icon):
        GLib.idle_add(self.show_message, title, text)

    def _on_about_clicked(self, *_):
        dialog = AboutDialog(self)
        dialog.present()

    def _on_custom_install_clicked(self, *_):
        win = CustomInstallDirectoryWindow(self)
        win.present()

    def _on_row_selected(self, *_):
        self._update_selection_dependent_buttons()

    def _on_install_location_changed(self, *_):
        idx = self.install_dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self._install_paths):
            return

        self._update_install_icon(idx)
        install_directory(self._install_paths[idx])
        self.refresh_installed_versions()

    def get_ctobjs_for_install_dir(self, path: str):
        install_loc = get_install_location_from_directory_name(path)
        return self.ct_loader.get_ctobjs(
            launcher=install_loc,
            advanced_mode='true' in config_advanced_mode().lower(),
        )

    def refresh_install_locations(self):
        self._install_paths = available_install_directories()
        self._display_index_map = []

        labels = []
        for path in self._install_paths:
            loc = get_install_location_from_directory_name(path)
            display = loc.get('display_name') or 'Custom'
            labels.append(f'{display} ({path})')
            self._display_index_map.append(path)

        model = Gtk.StringList.new(labels)
        self.install_dropdown.set_model(model)

        current = install_directory()
        if current in self._display_index_map:
            idx = self._display_index_map.index(current)
            self.install_dropdown.set_selected(idx)
            self._update_install_icon(idx)
        elif self._display_index_map:
            install_directory(self._display_index_map[0])
            self.install_dropdown.set_selected(0)
            self._update_install_icon(0)

    def _update_install_icon(self, index: int):
        if index < 0 or index >= len(self._install_paths):
            self.install_icon.set_from_icon_name('folder-symbolic')
            return

        install_loc = get_install_location_from_directory_name(self._install_paths[index])
        icon_name = install_loc.get('icon') or 'folder-symbolic'
        self.install_icon.set_from_icon_name(self._resolve_icon_name(icon_name))

    def _resolve_icon_name(self, icon_name: str) -> str:
        display = self.get_display()
        if display is None:
            return 'folder-symbolic'

        icon_theme = Gtk.IconTheme.get_for_display(display)
        if icon_theme and icon_theme.has_icon(icon_name):
            return icon_name

        # Normalize a few known app IDs to common symbolic icons if missing in theme.
        if 'steam' in icon_name.lower():
            if icon_theme and icon_theme.has_icon('steam-symbolic'):
                return 'steam-symbolic'
            return 'applications-games-symbolic'
        if 'lutris' in icon_name.lower():
            return 'applications-games-symbolic'
        if 'heroic' in icon_name.lower():
            return 'applications-games-symbolic'

        return 'folder-symbolic'

    def refresh_installed_versions(self):
        while True:
            row = self.listbox.get_row_at_index(0)
            if row is None:
                break
            self.listbox.remove(row)

        idx = self.install_dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self._install_paths):
            self.summary.set_text('No install locations found.')
            self.btn_remove.set_sensitive(False)
            self.btn_show_info.set_sensitive(False)
            return

        install_dir_path = self._install_paths[idx]
        ctools = get_installed_ctools(install_dir_path)

        self._list_index_map = ctools
        for ct in ctools:
            row = Adw.ActionRow()
            row.set_title(ct.displayname)
            subtitle = ct.version if ct.version else ct.install_folder
            row.set_subtitle(subtitle)
            self.listbox.append(row)

        self.summary.set_text(f'Installed versions: {len(ctools)}')
        self._update_selection_dependent_buttons()

    def _update_selection_dependent_buttons(self):
        has_selection = self._get_selected_ctool() is not None
        self.btn_remove.set_sensitive(has_selection)
        self.btn_show_info.set_sensitive(has_selection)

    def _get_selected_ctool(self):
        selected = self.listbox.get_selected_row()
        if selected is None:
            return None
        idx = selected.get_index()
        if idx < 0 or idx >= len(self._list_index_map):
            return None
        return self._list_index_map[idx]

    def _on_add_clicked(self, *_):
        idx = self.install_dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self._install_paths):
            self.show_message('Error', 'No valid install directory is selected.')
            return

        dialog = InstallDialog(parent=self, install_dir=self._install_paths[idx])
        dialog.present()

    def install_tool(self, ctobj: dict, version: str, target_dir: str):
        installer = ctobj['installer']

        if hasattr(installer, 'is_system_compatible') and not installer.is_system_compatible():
            self.show_message('Unsupported', f"{ctobj['name']} is not supported on this system.")
            return

        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self.progress.set_text('Preparing...')

        thread = threading.Thread(
            target=self._install_tool_thread,
            args=(installer, ctobj['name'], version, target_dir),
            daemon=True,
        )
        thread.start()

    def _install_tool_thread(self, installer, tool_name: str, version: str, target_dir: str):
        try:
            ok = installer.get_tool(version, os.path.expanduser(target_dir), TEMP_DIR)
            if not ok:
                GLib.idle_add(self.show_message, 'Install Failed', f'Failed to install {tool_name} {version}.')
        except Exception as e:
            GLib.idle_add(self.show_message, 'Install Failed', str(e))
        finally:
            GLib.idle_add(self.refresh_installed_versions)
            GLib.idle_add(self._set_progress_value, -1)

    def _on_remove_clicked(self, *_):
        ct = self._get_selected_ctool()
        if ct is None:
            self.show_message('Error', 'Please select a compatibility tool to remove.')
            return

        dialog = Adw.MessageDialog.new(
            self,
            'Remove version?',
            f'Are you sure you want to remove "{ct.displayname}"?',
        )
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('remove', 'Remove')
        dialog.set_response_appearance('remove', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', lambda d, r: self._on_remove_confirmed(d, r, ct))
        dialog.present()

    def _on_remove_confirmed(self, dialog, response: str, ct):
        dialog.close()
        if response != 'remove':
            return

        install_path = os.path.join(ct.install_dir, ct.install_folder)

        if 'steamtinkerlaunch' in ct.install_folder.lower():
            remove_steamtinkerlaunch(compat_folder=install_path, remove_config=False)
        elif os.path.exists(install_path):
            shutil.rmtree(install_path)

        self.refresh_installed_versions()

    def _on_show_info_clicked(self, *_):
        ct = self._get_selected_ctool()
        if ct is None:
            self.show_message('Error', 'Please select a compatibility tool first.')
            return

        detail = '\n'.join([
            f'Name: {ct.displayname}',
            f'Version: {ct.version or "Unknown"}',
            f'Install folder: {ct.install_folder}',
            f'Install path: {os.path.join(ct.install_dir, ct.install_folder)}',
        ])
        self.show_message('Compatibility Tool Info', detail)

    def _on_show_game_list_clicked(self, *_):
        idx = self.install_dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self._install_paths):
            self.show_message('Game List', 'No install location selected.')
            return

        install_loc = get_install_location_from_directory_name(self._install_paths[idx])
        dialog = GameListDialog(self, install_loc)
        dialog.present()

    def show_message(self, title: str, body: str):
        dialog = Adw.MessageDialog.new(self, title, body)
        dialog.add_response('ok', 'OK')
        dialog.set_default_response('ok')
        dialog.set_close_response('ok')
        dialog.connect('response', lambda d, _: d.close())
        dialog.present()
        return False


class ProtonUpGtkApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        win = self.props.active_window
        if win is None:
            win = MainWindow(self)
        win.present()


def main():
    app = ProtonUpGtkApp()
    app.run(None)


if __name__ == '__main__':
    main()

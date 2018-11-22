import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GObject

from menu import DbusMenu
from fuzzy import FuzzyMatch


class CommandListItem(Gtk.ListBoxRow):

  value = GObject.Property(type=str)
  index = GObject.Property(type=int)

  def __init__(self, *args, **kwargs):
    super(Gtk.ListBoxRow, self).__init__(*args, **kwargs)

    self.set_can_focus(False)

    self.value = self.get_property('value')
    self.index = self.get_property('index')
    self.fuzzy = FuzzyMatch(text=self.value)

    self.label = Gtk.Label(margin=6, margin_left=10, margin_right=10)
    self.label.set_justify(Gtk.Justification.LEFT)
    self.label.set_halign(Gtk.Align.START)
    self.label.set_label(self.value)

    self.add(self.label)
    self.show_all()

  def position(self, query):
    return self.fuzzy.score(query) if bool(query) else 0

  def visibility(self, query):
    return self.fuzzy.score(query) > -1 if bool(query) else True


class CommandList(Gtk.ListBox):

  menu_actions = GObject.Property(type=object)

  def __init__(self, *args, **kwargs):
    super(Gtk.ListBox, self).__init__(*args, **kwargs)

    self.select_value = ''
    self.filter_value = ''
    self.visible_rows = []
    self.selected_row = 0
    self.selected_obj = None
    self.menu_actions = self.get_property('menu-actions')

    self.set_sort_func(self.sort_function)
    self.set_filter_func(self.filter_function)

    self.connect('row-selected', self.on_row_selected)
    self.connect('notify::menu-actions', self.on_menu_actions_notify)

  def set_filter_value(self, value=None):
    self.visible_rows = []
    self.filter_value = value

    self.unselect_all()
    self.invalidate_filter()
    self.invalidate_sort()
    self.invalidate_selection()

  def invalidate_selection(self):
    adjust = self.get_adjustment()
    self.select_row_by_index(0)

    return adjust.set_value(0) if adjust else False

  def execute_command(self):
    if self.select_value:
      self.dbus_menu.activate(self.select_value)

  def append_visible_row(self, row, visibility):
    if visibility:
      self.visible_rows.append(row)

  def select_row_by_index(self, index):
    if index in range(0, len(self.visible_rows)):
      self.selected_row = index
      self.selected_obj = self.visible_rows[index]

      self.selected_obj.activate()

  def select_prev_row(self):
    self.select_row_by_index(self.selected_row - 1)

  def select_next_row(self):
    self.select_row_by_index(self.selected_row + 1)

  def sort_function(self, prev_item, next_item):
    prev_score = prev_item.position(self.select_value)
    next_score = next_item.position(self.select_value)

    score_diff = prev_score - next_score
    index_diff = prev_item.index - next_item.index

    return index_diff if score_diff == 0 else index_diff

  def filter_function(self, item):
    visible = item.visibility(self.filter_value)

    if visible:
      self.visible_rows.append(item)

    return visible

  def on_row_selected(self, listbox, item):
    self.select_value = item.value if item else ''

  def on_menu_actions_notify(self, *args):
    self.foreach(lambda item: item.destroy())

    for index, value in enumerate(self.menu_actions):
      command = CommandListItem(value=value, index=index)
      self.add(command)


class CommandWindow(Gtk.ApplicationWindow):

  menu_actions = GObject.Property(type=object)

  def __init__(self, *args, **kwargs):
    super(Gtk.ApplicationWindow, self).__init__(*args, **kwargs)

    self.skip_taskbar_hint   = True
    self.destroy_with_parent = True
    self.modal               = True
    self.window_position     = Gtk.WindowPosition.CENTER_ON_PARENT
    self.type_hint           = Gdk.WindowTypeHint.DIALOG
    self.menu_actions        = self.get_property('menu-actions')

    self.set_default_size(640, 250)
    self.set_size_request(640, 250)

    self.command_list = CommandList(menu_actions=self.menu_actions)
    self.command_list.invalidate_selection()

    self.search_entry = Gtk.SearchEntry(hexpand=True, margin=2)
    self.search_entry.connect('changed', self.on_search_entry_changed)

    self.scrolled_window = Gtk.ScrolledWindow(hadjustment=None, vadjustment=None)
    self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    self.scrolled_window.add(self.command_list)

    self.header_bar = Gtk.HeaderBar(spacing=0)
    self.header_bar.set_custom_title(self.search_entry)

    self.set_titlebar(self.header_bar)
    self.add(self.scrolled_window)

    self.set_dark_variation()

    self.connect('show', self.on_window_show)
    self.connect('notify::menu-actions', self.on_menu_actions_notify)

  def set_dark_variation(self):
    settings = Gtk.Settings.get_default()
    settings.set_property('gtk-application-prefer-dark-theme', True)

  def on_window_show(self, window):
    self.search_entry.grab_focus()

  def on_search_entry_changed(self, *args):
    search_value = self.search_entry.get_text()
    self.command_list.set_filter_value(search_value)

  def on_menu_actions_notify(self, *args):
    self.command_list.set_property('menu-actions', self.menu_actions)


class ModalMenu(Gtk.Application):

  def __init__(self, *args, **kwargs):
    kwargs['application_id'] = 'org.hardpixel.gnomeHUD'
    super(Gtk.Application, self).__init__(*args, **kwargs)

    self.dbus_menu = DbusMenu()

    self.set_accels_for_action('app.start', ['<Ctrl><Alt>space'])
    self.set_accels_for_action('app.quit', ['Escape'])
    self.set_accels_for_action('app.prev', ['Up'])
    self.set_accels_for_action('app.next', ['Down'])
    self.set_accels_for_action('app.execute', ['Return'])

  def add_simple_action(self, name, callback):
    action = Gio.SimpleAction.new(name, None)
    action.connect('activate', callback)
    self.add_action(action)

  def do_startup(self):
    Gtk.Application.do_startup(self)

    self.add_simple_action('start', self.on_show_window)
    self.add_simple_action('quit', self.on_hide_window)
    self.add_simple_action('prev', self.on_prev_command)
    self.add_simple_action('next', self.on_next_command)
    self.add_simple_action('execute', self.on_execute_command)

  def do_activate(self):
    self.window = CommandWindow(application=self, title='gnomeHUD')
    self.window.set_property('menu-actions', self.dbus_menu.actions)
    self.window.show_all()

  def on_show_window(self, *args):
    self.window.show()

  def on_hide_window(self, *args):
    self.window.hide()
    self.quit()

  def on_prev_command(self, *args):
    self.window.command_list.select_prev_row()

  def on_next_command(self, *args):
    self.window.command_list.select_next_row()

  def on_execute_command(self, *args):
    self.window.command_list.execute_command()
    self.quit()


if __name__ == '__main__':
  modal = ModalMenu()
  modal.run()

"""GUI-related helper methods"""

from gettext import gettext as _

import gtk
import gobject
import StringIO

import advene.util.vlclib as vlclib

def png_to_pixbuf (png_data):
    """Load PNG data into a pixbuf
    """
    loader = gtk.gdk.PixbufLoader ('png')
    loader.write (png_data, len (png_data))
    pixbuf = loader.get_pixbuf ()
    loader.close ()
    return pixbuf

def generate_list_model(elements, controller=None, active_element=None):
    """Update a TreeModel matching the elements list.

    Element 0 is the label.
    Element 1 is the element (stbv).
    """
    store=gtk.ListStore(str, object)
    active_iter=None
    for e in elements:
        i=store.append( ( vlclib.get_title(controller, e), e ) )
        if e == active_element:
            active_iter=i
    return store, active_iter
                

def list_selector(title=None,
                  text=None,
                  members=None,
                  controller=None):
    """Pick an element from a list.

    vlclib.get_title is invoked to get a textual representation of
    the elements of members.

    Return None if the action is cancelled.
    """
    store, i=generate_list_model(members, controller=controller)

    combobox=gtk.ComboBox(store)
    cell = gtk.CellRendererText()
    combobox.pack_start(cell, True)
    combobox.add_attribute(cell, 'text', 0)
    combobox.set_active(-1)
    if i is None:
        i = store.get_iter_first()
    combobox.set_active_iter(i)
    
    d = gtk.Dialog(title=title,
                   parent=None,
                   flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                   buttons=( gtk.STOCK_OK, gtk.RESPONSE_ACCEPT,
                             gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT ))

    if text is not None:
        l=gtk.Label(text)
        l.show()
        d.vbox.add(l)

    d.vbox.add(combobox)
    combobox.show_all()

    res=d.run()
    retval=None
    if res == gtk.RESPONSE_ACCEPT:
        retval=combobox.get_model().get_value(combobox.get_active_iter(), 1)
    d.destroy()
    return retval

def yes_no_cancel_popup(title=None,
                        text=None):
    """Build a Yes-No-Cancel popup window.

    Return codes are in (gtk.RESPONSE_YES, gtk.RESPONSE_NO, gtk.RESPONSE_CANCEL)
    """
    d = gtk.Dialog(title=title,
                   parent=None,
                   flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                   buttons=( gtk.STOCK_YES, gtk.RESPONSE_YES,
                             gtk.STOCK_NO, gtk.RESPONSE_NO,
                             gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL ))

    hb=gtk.HBox()
    hb.show()
    d.vbox.add(hb)
    
    i=gtk.Image()
    i.set_from_stock(gtk.STOCK_DIALOG_QUESTION, gtk.ICON_SIZE_DIALOG)
    i.show()
    hb.pack_start(i, expand=False)
    
    if text is not None:
        l=gtk.Label(text)
        l.show()
        hb.add(l)

    retval=d.run()
    d.destroy()
    return retval


def entry_dialog(title=None,
                 text=None,
                 default=""):
    """Display a dialog to enter a short text.
    """
    d = gtk.Dialog(title=title,
                   parent=None,
                   flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                   buttons=( gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                             gtk.STOCK_OK, gtk.RESPONSE_ACCEPT,
                             ))
    if text:
        l=gtk.Label(text)
        l.show()
        d.vbox.add(l)

    e=gtk.Entry()
    e.show()
    if default:
        e.set_text(default)
    
    def keypressed_cb(widget=None, event=None):
        if event.keyval == gtk.keysyms.Return:
            # Validate the activated entry
            d.response(gtk.RESPONSE_ACCEPT)
            return True
        return False
    e.connect("key_press_event", keypressed_cb)

    d.vbox.add(e)

    res=d.run()
    ret=None
    if res == gtk.RESPONSE_ACCEPT:
        try:
            ret=e.get_text()
        except ValueError:
            ret=None
    else:
        ret=None

    d.destroy()
    return ret

def build_optionmenu(elements, current, on_change_element, editable=True):
    """Build an ComboBox.

    elements is a dict holding (key, values) where the values will be used as labels
    current is the current activated element (i.e. one of the keys)
    on_change_element is the method which will be called upon option modification.

    Its signature is:

    ``def on_change_element([self,] element):``
    """
    def change_cb(combobox, on_change_element):
        i=combobox.get_active_iter()
        element=combobox.get_model().get_value(i, 1)
        on_change_element(element)
        return True

    store=gtk.ListStore(str, object)
    active_iter=None
    for k, v in elements.iteritems():
        i=store.append( (v, k) )
        if k == current:
            active_iter=i

    optionmenu = gtk.ComboBox(model=store)
    cell = gtk.CellRendererText()
    optionmenu.pack_start(cell, True)
    optionmenu.add_attribute(cell, 'text', 0)
    optionmenu.set_active_iter(active_iter)
    optionmenu.connect("changed", change_cb, on_change_element)
    optionmenu.set_sensitive(editable)
    optionmenu.show_all()
    return optionmenu

def get_filename(title="Open a file",
                 action=gtk.FILE_CHOOSER_ACTION_OPEN,
                 button=gtk.STOCK_OPEN,
                 default_dir=None):
    fs=gtk.FileChooserDialog(title=title,
                             parent=None,
                             action=action,
                             buttons=( button,
                                       gtk.RESPONSE_OK,
                                       gtk.STOCK_CANCEL,
                                       gtk.RESPONSE_CANCEL ))
    if default_dir:
        fs.set_current_folder(default_dir)
    res=fs.run()
    filename=None
    if res == gtk.RESPONSE_OK:
        filename=fs.get_filename()
    fs.destroy()
    
    return filename

class CategorizedSelector:
    """Widget displaying items sorted along categories.

    We use a treeview to display elements.

    @ivar elements: list of  elements
    @type elements: list
    @ivar categories: list of categories
    @type categories: list
    @ivar current: current element
    @type current: object
    @ivar description_getter: method to get the description of the element or the category
    @type description_getter: method
    @ivar category_getter: method to get the category of the element
    @type category_getter: method
    @ivar callback: method to be called upon modification
    @type callback: method
    @ivar editable: indicates if the data is editable
    @type editable: boolean
    @ivar button: a gtk.Button with a label matching the selected value
    @type button: gtk.Button
    """
    COLUMN_ELEMENT=0
    COLUMN_LABEL=1
    COLUMN_MODE=2
    def __init__(self, title=_("Select an element"),
                 elements=None, categories=None, current=None,
                 description_getter=None, category_getter=None, callback=None,
                 editable=True):
        self.title=title
        self.elements=elements
        self.categories=categories
        self.current=current
        self.description_getter=description_getter
        self.category_getter=category_getter
        self.callback=callback
        self.editable=editable
        self.store=None
        # A button representing the current element
        self.button=None
        # The popup window
        self.popup=None
        self.widget=self.build_widget()

    def build_liststore(self):
        # We store the object itself and its representation
        store=gtk.TreeStore(
            gobject.TYPE_PYOBJECT,
            gobject.TYPE_STRING,
            gobject.TYPE_INT,
            )

        catrow={}
        for i in self.categories:
            catrow[i]=store.append(parent=None,
                                   row=[i,
                                        self.description_getter(i),
                                        gtk.CELL_RENDERER_MODE_INERT])
        currentrow=None
        for e in self.elements:
            row=store.append(parent=catrow[self.category_getter(e)],
                             row=[e,
                                  self.description_getter(e),
                                  gtk.CELL_RENDERER_MODE_ACTIVATABLE])
            if e == self.current:
                currentrow=row
        return store, currentrow

    def row_activated_cb(self, treeview, path, column):
        element=treeview.get_model()[path][self.COLUMN_ELEMENT]
        if not element in self.elements:
            # It is a category
            return False
        self.update_element(element)
        # Hide the selection
        self.popup_hide()
        return True
        
    def build_widget(self):
        vbox=gtk.VBox()

        self.store, currentrow=self.build_liststore()

        treeview=gtk.TreeView(model=self.store)
        #treeview.connect("button_press_event", self.tree_view_button_cb)
        treeview.connect("row_activated", self.row_activated_cb)
        path=self.store.get_path(currentrow)
        treeview.expand_to_path(path)
        treeview.scroll_to_cell(path)
        treeview.set_cursor_on_cell(path)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_('Name'), renderer,
                                    text=self.COLUMN_LABEL,
                                    mode=self.COLUMN_MODE)
        column.set_resizable(True)
        treeview.append_column(column)
        
        vbox.add(treeview)

        hbox=gtk.HButtonBox()

        b=gtk.Button(stock=gtk.STOCK_OK)
        b.connect("clicked", lambda w: treeview.row_activated(*treeview.get_cursor()))
        hbox.add(b)
        b=gtk.Button(stock=gtk.STOCK_CANCEL)
        b.connect("clicked", lambda w: self.popup_hide())
        hbox.add(b)
        vbox.add(hbox)
        
        vbox.show_all()
        
        return vbox

    def get_button(self):
        """Return a button with the current element description as label.
        """
        if self.button is not None:
            return self.button
        b=gtk.Button(self.description_getter(self.current))
        if self.editable:
            b.connect("clicked", lambda w: self.popup_show())
        b.show()
        self.button=b
        return b

    def update_element(self, element=None):
        self.current=element
        if self.button is not None:
            self.button.set_label(self.description_getter(element))
        if self.callback is not None:
            self.callback(element)
        return True

    def popup_show(self):
        if self.popup is None:
            w=gtk.Window()
            w.set_title(self.title)
            w.add(self.widget)
            self.popup=w
        self.popup.set_position(gtk.WIN_POS_MOUSE)
        self.popup.show_all()
        return True

    def popup_hide(self):
        if self.popup is not None:
            self.popup.hide()
        return True


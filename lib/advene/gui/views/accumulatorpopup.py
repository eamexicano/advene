"""Accumulator popup.
"""

import sys
import time

import gtk
import gobject
import pango
#from threading import Lock

from gettext import gettext as _

import advene.gui.edit.elements
import advene.gui.edit.create
import advene.gui.popup

class DummyLock:
    def __init__(self):
        self.count=0
        
    def acquire(self):
        #print "acquire %d" % self.count
        self.count += 1
        return True

    def release(self):
        #print "release %d" % self.count
        self.count -= 1
        return True
    
class AccumulatorPopup:
    """View displaying a limited number of popups.
    """
    def __init__ (self, size=3, controller=None, autohide=False, container=None):
        self.size=size
        self.controller=controller
        self.container=container
        # Hide the window if there is no widget
        self.autohide = autohide

        self.new_color = gtk.gdk.color_parse ('tomato')
        self.old_color = gtk.Button().get_style().bg[0]        

        # List of tuples (widget, hidetime, frame)
        self.widgets=[]
        # Lock on self.widgets
        self.lock=DummyLock()
        
        self.window=self.build_widget()

    def undisplay_cb(self, button=None, widget=None):
        self.undisplay(widget)
        return True
    
    def display(self, widget=None, timeout=None, title=None):
        """Display the given widget.

        timeout is in ms.
        """
        if title is None:
            title="X"
        if len(self.widgets) >= self.size:
            # Remove the last one
            self.undisplay(self.widgets[0][0])
        if timeout is not None and timeout != 0:
            hidetime=time.time() + (long(timeout) / 1000.0)
        else:
            hidetime=None

        # Build a titled frame around the widget
        f=gtk.Frame()
        b=gtk.Button(title)
        b.connect("clicked", self.undisplay_cb, widget)
        self.set_color(b, self.new_color)
        f.set_label_widget(b)
        f.add(widget)

        self.lock.acquire()
        for t in self.widgets:
            self.set_color(t[2].get_label_widget(), self.old_color)
        self.widgets.append( (widget, hidetime, f) )
        self.widgets.sort(lambda a,b: cmp(a[1],b[1]))
        self.lock.release()
        self.hbox.pack_start(f, expand=False)

        f.show_all()
        self.show()
        return True

    def set_color(self, button, color):
        for style in (gtk.STATE_ACTIVE, gtk.STATE_NORMAL,
                      gtk.STATE_SELECTED, gtk.STATE_INSENSITIVE,
                      gtk.STATE_PRELIGHT):
            button.modify_bg (style, color)
    
    def get_popup_width(self):
        """Return the requested popup width

        According to the hbox size and the max number of popups.
        """
        return self.hbox.get_allocation().width / self.size
    
    def undisplay(self, widget=None):
        # Find the associated frame
        self.lock.acquire()
        
        frames=[ t for t in self.widgets if t[0] == widget ]
        if not frames:
            return True
        if len(frames) > 1:
            print "Inconsistency in accumulatorpopup"
        t=frames[0]
        self.widgets.remove(t)
        self.lock.release()
        
        # We found at least one (and hopefully only one) matching record
        t[2].destroy()
        if not self.widgets and self.autohide:
            self.window.hide()
        return True
    
    def hide(self, *p, **kw):
        self.window.hide()
        return True

    def show(self, *p, **kw):
        self.window.show_all()
        return True

    def update_position(self, pos):
        # This method is regularly called. We use it as a side-effect to
        # remove the widgets when the timeout expires.
        # We should do a loop to remove all expired widgets, but
        # in a first approximation, update_position will itself
        # quietly loop
        if self.widgets:
            self.lock.acquire()
            t=self.widgets[0][1]
            if t is not None and time.time() >= t:
                self.undisplay(self.widgets[0][0])
            self.lock.release()
        return True
    
    def build_widget(self):
        if self.container:
            window=self.container
        else:
            window = gtk.Window(gtk.WINDOW_TOPLEVEL)
            window.set_title (_("Popups"))

        f=gtk.Frame()
        f.set_label(_("Popups"))
        window.add(f)
        
        mainbox=gtk.VBox()
        f.add(mainbox)
        
        self.hbox = gtk.HBox()
        mainbox.add(self.hbox)

        if self.controller.gui:
            self.controller.gui.register_view (self)

        if self.container is None:
            window.connect ("destroy", lambda w: True)
            
            hb=gtk.HButtonBox()
            
            b=gtk.Button(stock=gtk.STOCK_CLOSE)
            b.connect("clicked", self.hide)
            hb.add(b)
        
            mainbox.pack_start(hb, expand=False)
        
        return window

    def get_widget (self):
        """Return the TreeView widget."""
        return self.window

    def popup(self):
        window.show_all()
        return window

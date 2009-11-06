# -*- coding: utf-8 -*-
#
# Advene: Annotate Digital Videos, Exchange on the NEt
# Copyright (C) 2008 Olivier Aubert <olivier.aubert@liris.cnrs.fr>
#
# Advene is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Advene is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Advene; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
"""Trace timeline.

This widget allows to present event history in a timeline view.
"""

import urllib
import gtk
import time
from gettext import gettext as _
from advene.model.fragment import MillisecondFragment
from advene.model.schema import Schema, AnnotationType, RelationType
from advene.model.annotation import Annotation, Relation
from advene.model.view import View
from math import floor
from advene.gui.views import AdhocView
#import advene.util.helper as helper
from advene.rules.elements import ECACatalog
import advene.core.config as config
from advene.gui.widget import TimestampRepresentation
from advene.gui.util import dialog, get_small_stock_button

try:
    import goocanvas
    from goocanvas import Group
except ImportError:
    # Goocanvas is not available. Define some globals in order not to
    # fail the module loading, and use them as a guard in register()
    goocanvas=None
    Group=object

def register(controller):
    if goocanvas is None:
        controller.log("Cannot register TraceTimeline: the goocanvas python module does not seem to be available.")
    else:
        controller.register_viewclass(TraceTimeline)

name="Trace Timeline view"
ACTION_COLORS=[0x000088AA, 0x008800AA, 0x880000AA, 0x008888FF, 0x880088FF, 0x0000FFAA, 0x00FF00AA, 0xFF0000FF, 0x888800FF, 0xFF00FFFF, 0x00FFFFFF, 0xFFFF00FF, 0x00FF88FF, 0xFF0088FF, 0x0088FFFF, 0x8800FFFF, 0x88FF00FF, 0xFF8800FF]
ACTIONS=[]
INCOMPLETE_OPERATIONS_NAMES = {
            'EditSessionStart': _('Beginning edition'),
            'ElementEditBegin': _('Beginning edition'),
            'ElementEditDestroy': _('Canceling edition'),
            'ElementEditCancel': _('Canceling edition'),
            'EditSessionEnd': _('Canceling edition'),
            'ElementEditEnd': _('Ending edition'),
            'PlayerSet': _('Moving to'),
        }

class TraceTimeline(AdhocView):
    view_name = _("Traces")
    view_id = 'trace2'
    tooltip=("Traces of Advene Events in a Timeline")
    def __init__ (self, controller=None, parameters=None, package=None):
        super(TraceTimeline, self).__init__(controller=controller)
        self.close_on_package_load = False
        self.tracer = self.controller.tracers[0]
        self.__package=package
        if self.tracer.trace.levels['events']:
            self.start_time = self.tracer.trace.levels['events'][0].time
        else:
            self.start_time = config.data.startup_time
        #self.contextual_actions = (
        #    (_("Refresh"), self.refresh),
        #    )
        if package is None and controller is not None:
            self.__package=controller.package
        self.drag_coordinates=None

        self.active_trace = None
        
        # Header canvas
        self.head_canvas = None
        # Main timeline canvas
        self.canvas = None
        # Contextualizing document canvas
        self.doc_canvas = None
        self.display_values = {} # name : (canvasY, timefactor, obj_l, center value)
        self.selection=[ 0, 0, 0, 0 ]
        self.sel_frame=None
        self.inspector = None
        self.btnl = None
        self.btnlm = None
        self.link_mode = 0
        self.lasty=0
        self.canvasX = None
        self.doc_canvas_X = 100
        self.canvasY = 1
        self.head_canvasY = 25
        self.doc_canvas_Y = 45
        self.docgroup = None
        self.obj_l = 5
        self.incr = 500
        self.timefactor = 100
        self.autoscroll = True
        self.links_locked = False
        self.sw = None
        self.cols={}
        self.tracer.register_view(self)
        while ACTIONS:
            ACTIONS.pop(-1)
        for act in self.tracer.action_types:
            self.cols[act] = (None, None)
            ACTIONS.append(act)
        self.col_width = 80
        self.colspacing = 5
        self.widget = self.build_widget()
        self.widget.connect("destroy", self.destroy)
        self.populate_head_canvas()
        self.widget.show_all()
        self.active_trace = self.tracer.trace
        self.receive(self.active_trace)

    def select_trace(self, trace):
        if isinstance(trace, (int, long)):
            # Interpret it as an index into the self.tracers.traces
            # list
            trace=self.tracer.traces[trace]
        # unlock inspector
        if self.links_locked:
            self.toggle_lock()
            self.inspector.clean()
        # save zoom values
        h = self.canvas.get_allocation().height
        va=self.sw.get_vadjustment()
        vc = (va.value + h/2.0) * self.timefactor
        self.display_values[self.active_trace.name] = (self.canvasY, self.timefactor, self.obj_l, vc)
        self.active_trace = trace
        # redraw docgroup
        self.docgroup.redraw(self.active_trace)
        # restore zoom values if any
        if self.active_trace.name in self.display_values.keys():
            (self.canvasY, self.timefactor, self.obj_l, vc) = self.display_values[self.active_trace.name]
            self.canvas.set_bounds (0,0,self.canvasX,self.canvasY)
            self.refresh(center = vc)
        else:
            self.refresh()

    def build_widget(self):
        mainbox = gtk.VBox()

        # trace selector
        def trace_changed(w):
            self.select_trace(w.get_active())
            return True
        self.selector_box = gtk.HBox()
        self.trace_selector = dialog.list_selector_widget(
            members= [( n, _("%(name)s (%(index)d)") % {
                        'name': t.name, 
                        'index': n
                        }) for (n, t) in enumerate(self.tracer.traces)],
            preselect=0,
            callback=trace_changed)
        #self.trace_selector.set_size_request(70,-1)
        self.selector_box.pack_start(self.trace_selector, expand=True)
        self.remove_trace_button = get_small_stock_button(gtk.STOCK_CANCEL)
        def remove_trace(button, event):
            tr = self.trace_selector.get_active()
            if tr > 0:
                self.tracer.remove_trace(tr)
                mod= self.trace_selector.get_model()
                if len(self.tracer.traces)<len(mod):
                    mod.remove(mod.get_iter(tr))
                    self.trace_selector.set_active(tr-1)
                #self.select_trace(tr-1)
            
        self.remove_trace_button.connect('button-press-event', remove_trace)
        self.selector_box.pack_start(self.remove_trace_button, expand=False)
        mainbox.pack_start(self.selector_box, expand=False)

        quicksearch_options = [False, ['oname','oid','ocontent']] # exact search, where to search
        self.quicksearch_button=get_small_stock_button(gtk.STOCK_FIND)
        self.quicksearch_entry=gtk.Entry()
        self.quicksearch_entry.set_text(_('Search'))
        def do_search(button, event, options):
            tr=self.tracer.search(self.active_trace, unicode(self.quicksearch_entry.get_text(),'utf-8'), options[0], options[1])
            mod= self.trace_selector.get_model()
            if len(self.tracer.traces)>len(mod):
                n = len(self.tracer.traces)-1
                mod.append((_("%(name)s (%(index)s)") % {
                        'name': self.tracer.traces[n].name, 
                        'index': n}, 
                           n, None ))
                self.trace_selector.set_active(n)
            #self.select_trace(tr)
        self.quicksearch_button.connect('button-press-event', do_search, quicksearch_options)
        def is_focus(w, event):
            if w.is_focus() :
                return False
            w.select_region(0, len(w.get_text()))
            w.grab_focus()
            return True
        def is_typing(w, event):
            #if return is hit, activate quicksearch_button
            if event.keyval == gtk.keysyms.Return:
                self.quicksearch_button.activate()
        self.quicksearch_entry.connect('button-press-event', is_focus)
        self.quicksearch_entry.connect('key-press-event', is_typing)
        self.search_box = gtk.HBox()
        self.search_box.pack_start(self.quicksearch_entry, expand=False)
        self.search_box.pack_start(self.quicksearch_button, expand=False)
        mainbox.pack_start(self.search_box, expand=False)

        toolbox = gtk.Toolbar()
        toolbox.set_orientation(gtk.ORIENTATION_HORIZONTAL)
        toolbox.set_style(gtk.TOOLBAR_ICONS)
        mainbox.pack_start(toolbox, expand=False)

        bx = gtk.HPaned()
        mainbox.pack_start(bx, expand=True)

        timeline_box=gtk.VBox()
        bx.pack1(timeline_box, resize=False, shrink=False)

        scrolled_win = gtk.ScrolledWindow ()
        self.sw = scrolled_win
        self.sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_ALWAYS)

        self.head_canvas = goocanvas.Canvas()
        c = len(self.cols)
        self.canvasX = c*(self.col_width+self.colspacing)
        self.head_canvas.set_bounds (0,0,self.canvasX,self.head_canvasY)
        self.head_canvas.set_size_request(-1, self.head_canvasY)
        timeline_box.pack_start(self.head_canvas, expand=False, fill=False)

        self.canvas = goocanvas.Canvas()
        self.canvas.set_bounds (0, 0,self.canvasX, self.canvasY)
        self.canvas.set_size_request(200, 25) # important to force a minimum size (else we could have problem with radius of objects < 0)

        self.doc_canvas = goocanvas.Canvas()
        self.doc_canvas.set_bounds(0,0, self.doc_canvas_X, self.doc_canvas_Y)
        self.doc_canvas.set_size_request(-1, self.doc_canvas_Y)
        self.docgroup = DocGroup(controller=self.controller, canvas=self.doc_canvas, name="Nom du film", x = 15, y=10, w=self.doc_canvas_X-30, h=self.doc_canvas_Y-25, fontsize=8, color_c=0x00000050)
        self.canvas.get_root_item().connect('button-press-event', self.canvas_clicked)
        self.canvas.get_root_item().connect('button-release-event', self.canvas_release)
        def canvas_resize(w, alloc):
            self.canvasX = alloc.width-20.0
            self.col_width = (self.canvasX)//len(self.cols)-self.colspacing
            #redraw head_canvas
            self.head_canvas.set_bounds (0, 0, self.canvasX, self.head_canvasY)
            self.redraw_head_canvas()
            #redraw canvas
            self.canvas.set_bounds (0, 0, self.canvasX, self.canvasY)
            h = self.canvas.get_allocation().height
            va=scrolled_win.get_vadjustment()
            vc = (va.value + h/2.0) * self.timefactor
            self.refresh(action=None, center=vc)
            #print alloc.width
        self.head_canvas.connect('size-allocate', canvas_resize)
        def doc_canvas_resize(w, alloc):
            #redraw doc_canvas
            self.doc_canvas_X = alloc.width
            self.doc_canvas_Y = alloc.height
            self.doc_canvas.set_bounds(0,0, self.doc_canvas_X, self.doc_canvas_Y)
            self.docgroup.rect.remove()
            self.docgroup.w = self.doc_canvas_X-30
            self.docgroup.h = self.doc_canvas_Y-25
            self.docgroup.rect = self.docgroup.newRect()
            self.docgroup.redraw(self.active_trace)
        self.doc_canvas.connect('size-allocate', doc_canvas_resize)
        scrolled_win.add(self.canvas)

        timeline_box.add(scrolled_win)

        mainbox.pack_start(gtk.HSeparator(), expand=False, fill=False)

        mainbox.pack_start(self.doc_canvas, expand=False, fill=True)

        btnm = gtk.ToolButton(stock_id=gtk.STOCK_ZOOM_OUT)
        btnm.set_tooltip_text(_('Zoom out'))
        btnm.set_label('')
        toolbox.insert(btnm, -1)

        btnp = gtk.ToolButton(stock_id=gtk.STOCK_ZOOM_IN)
        btnp.set_tooltip_text(_('Zoom in'))
        btnp.set_label('')
        toolbox.insert(btnp, -1)

        btnc = gtk.ToolButton(stock_id=gtk.STOCK_ZOOM_100)
        btnc.set_tooltip_text(_('Zoom 100%'))
        btnc.set_label('')
        toolbox.insert(btnc, -1)
        self.btnl = gtk.ToolButton()
        self.btnl.set_tooltip_text(_('Toggle links lock'))
        #self.btnl.set_label(_('Unlocked'))
        img = gtk.Image()
        img.set_from_file(config.data.advenefile( ( 'pixmaps', 'unlocked.png') ))
        self.btnl.set_icon_widget(img)
        toolbox.insert(self.btnl, -1)
        self.btnl.connect('clicked', self.toggle_lock)
        #btn to change link mode
        b = gtk.ToolButton(label='L')
        b.set_tooltip_text(_('Toggle link mode'))
        toolbox.insert(b, -1)
        b.connect('clicked', self.toggle_link_mode)

        def open_trace(b):
            fname=dialog.get_filename(title=_("Open a trace file"),
                                   action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                   button=gtk.STOCK_OPEN,
                                   default_dir=config.data.path['settings'],
                                   filter='any')
            if not fname:
                return True
            # FIXME: import_trace should return the trace reference,
            self.tracer.import_trace(fname)
            # Refresh combo box
            self.receive(self.tracer.traces[-1])
            self.trace_selector.set_active(len(self.tracer.traces) - 1)
            return True

        b=gtk.ToolButton(stock_id=gtk.STOCK_OPEN)
        b.set_tooltip_text(_('Open an existing trace'))
        toolbox.insert(b, -1)
        b.connect('clicked', open_trace)

        # Export trace
        btne = gtk.ToolButton(stock_id=gtk.STOCK_SAVE)
        btne.set_tooltip_text(_('Save trace'))
        toolbox.insert(btne, -1)
        btne.connect('clicked', self.export)
        #preselect= 0,
        #callback=refresh        
        self.inspector = Inspector(self.controller)
        bx.pack2(self.inspector)

        def on_background_scroll(widget, event):
            zoom=event.state & gtk.gdk.CONTROL_MASK
            a = None
            if zoom:
                center = event.y * self.timefactor
                if event.direction == gtk.gdk.SCROLL_DOWN:
                    zoom_out(widget, center)
                elif  event.direction == gtk.gdk.SCROLL_UP:
                    zoom_in(widget, center)
                return
            elif event.state & gtk.gdk.SHIFT_MASK:
                # Horizontal scroll
                a = scrolled_win.get_hadjustment()
                incr = a.step_increment
            else:
                # Vertical scroll
                a = scrolled_win.get_vadjustment()
                incr = a.step_increment

            if event.direction == gtk.gdk.SCROLL_DOWN:
                val = a.value + incr
                if val > a.upper - a.page_size:
                    val = a.upper - a.page_size
                elif val < a.lower:
                    val = a.lower
                if val != a.value:
                    a.value = val
            elif event.direction == gtk.gdk.SCROLL_UP:
                val = a.value - incr
                if val < a.lower:
                    val = a.lower
                elif val > a.upper - a.page_size:
                    val = a.upper - a.page_size
                if val != a.value:
                    a.value = val
            return True
        self.canvas.connect('scroll-event', on_background_scroll)

        def on_background_motion(widget, event):
            if not event.state & gtk.gdk.BUTTON1_MASK:
                return False
            if event.state & gtk.gdk.SHIFT_MASK:
                # redraw selection frame
                if self.selection[0]==0 and self.selection[1]==0:
                    self.selection[0]=event.x
                    self.selection[1]=event.y
                p = goocanvas.Points([(self.selection[0],self.selection[1]),(self.selection[0],event.y),(event.x,event.y),(event.x,self.selection[1])])
                if self.sel_frame is not None:
                    self.sel_frame.props.points = p
                else:
                    self.sel_frame=goocanvas.Polyline (parent = self.canvas.get_root_item(),
                                        close_path = True,
                                        points = p,
                                        stroke_color = 0xFFFFFFFF,
                                        line_width = 1.0,
                                        start_arrow = False,
                                        end_arrow = False,
                                        )
                return
            #if self.dragging:
            #    return False
            if not self.drag_coordinates:
                self.drag_coordinates=(event.x_root, event.y_root)
                self.widget.get_parent_window().set_cursor(gtk.gdk.Cursor(gtk.gdk.DIAMOND_CROSS))
                #curseur grab
                return False
            x, y = self.drag_coordinates
            wa=widget.get_allocation()
            a=scrolled_win.get_hadjustment()
            v=a.value + x - event.x_root
            if v > a.lower and v+wa.width < a.upper:
                a.value=v
            a=scrolled_win.get_vadjustment()
            v=a.value + y - event.y_root
            if v > a.lower and v+wa.height < a.upper:
                a.value=v

            self.drag_coordinates= (event.x_root, event.y_root)
            return False
        self.canvas.connect('motion-notify-event', on_background_motion)

        def on_background_button_release(widget, event):
            if event.button == 1:
                self.drag_coordinates=None
                self.widget.get_parent_window().set_cursor(None)
                #curseur normal
            return False
        self.canvas.connect('button-release-event', on_background_button_release)

        def zoom_out(w, center_v=None):
            h = self.canvas.get_allocation().height
            if h/float(self.canvasY)>=0.8:
                zoom_100(w)
            else:
                va=scrolled_win.get_vadjustment()
                vc=0
                if center_v is None:
                    vc = (va.value + h/2.0) * self.timefactor
                else:
                    vc = center_v
                self.canvasY *= 0.8
                self.timefactor *= 1.25
                self.obj_l *= 0.8
                #print "%s" % (self.timefactor)
                self.canvas.set_bounds (0,0,self.canvasX,self.canvasY)
                self.refresh(center = vc)
        btnm.connect('clicked', zoom_out)

        def zoom_in(w, center_v=None):
            h = self.canvas.get_allocation().height
            va=scrolled_win.get_vadjustment()
            if center_v is None:
                vc = (va.value + h/2.0) * self.timefactor
            else:
                vc = center_v
            self.canvasY *= 1.25
            self.timefactor *= 0.8
            self.obj_l *= 1.25
            #print "%s" % (self.timefactor)
            self.canvas.set_bounds (0,0,self.canvasX,self.canvasY)
            self.refresh(center = vc)
        btnp.connect('clicked', zoom_in)

        def zoom_100(w):
            wa = self.canvas.get_allocation()
            self.canvasY = wa.height-10.0 # -10 pour des raisons obscures ...
            if 'actions' in self.active_trace.levels.keys() and self.active_trace.levels['actions']:
                a = self.active_trace.levels['actions'][-1].activity_time[1]
                for act in self.active_trace.levels['actions']:
                    if act.activity_time[1]>a:
                        a=act.activity_time[1]
                self.timefactor = a/(self.canvasY)
                self.obj_l = 5000.0/self.timefactor
            else:
                self.timefactor = 1000
                self.obj_l = 5
            #print self.timefactor
            self.canvas.set_bounds(0,0,self.canvasX, self.canvasY)
            self.refresh()
        btnc.connect('clicked', zoom_100)

        bx.set_position(self.canvasX+15)
        return mainbox

    def export(self, w):
        fname = self.tracer.export()
        d = gtk.Dialog(title=_("Exporting traces"),
                       parent=None,
                       flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                       buttons=( gtk.STOCK_OK, gtk.RESPONSE_OK
                                 ))
        l=gtk.Label(_("Export done to\n%s") % fname)
        l.set_selectable(True)
        l.set_line_wrap(True)
        l.show()
        d.vbox.pack_start(l, expand=False)
        d.vbox.show_all()
        d.show()
        res=d.run()
        d.destroy()
        return

    def toggle_link_mode(self, w):
        if self.link_mode == 0:
            self.link_mode = 1
            w.set_label('H')
        else:
            self.link_mode = 0
            w.set_label('L')
        i=0
        root = self.canvas.get_root_item()
        while i < root.get_n_children():
            go = root.get_child(i)
            if isinstance(go, ObjGroup) or isinstance(go, EventGroup):
                go.link_mode=self.link_mode
            i+=1
        return

    def zoom_on(self, w=None, canvas_item=None):
        min_y = -1
        max_y = -1
        if hasattr(canvas_item, 'rect'):
            # action
            min_y = canvas_item.rect.get_bounds().y1
            max_y = canvas_item.rect.get_bounds().y2
        elif hasattr(canvas_item, 'rep'):
            obj_id = canvas_item.cobj['id']
            if obj_id is None:
                return
            i=0
            root = self.canvas.get_root_item()
            egl=[]
            while i < root.get_n_children():
                eg = root.get_child(i)
                if isinstance(eg, EventGroup) and eg.objs is not None:
                    egl.append(eg)
                i+=1
            for c in egl:
                if obj_id in c.objs.keys():
                    obj_gr = c.objs[obj_id][0]
                    if obj_gr is None:
                        y_mi = c.rect.get_bounds().y1
                        y_ma = c.rect.get_bounds().y1 + c.rect.props.height
                    else:
                        y_mi = obj_gr.y-obj_gr.r
                        y_ma = obj_gr.y+obj_gr.r
                    if min_y == -1:
                        min_y = y_mi
                    min_y = min(min_y, y_mi)
                    max_y = max(max_y, y_ma)
                    
        #print 'y1 %s y2 %s' % (min_y, max_y)
        h = self.canvas.get_allocation().height
        # 20.0 to keep a little space between border and object
        va=self.sw.get_vadjustment()
        rapp = (20.0 + max_y - min_y) / h
        vc = self.timefactor * ((min_y + max_y) / 2.0) * (va.upper / self.canvasY)
        self.timefactor = rapp * self.timefactor
        self.canvasY = rapp * self.canvasY
        self.obj_l = rapp * self.obj_l
        self.canvas.set_bounds (0,0,self.canvasX,self.canvasY)
        self.refresh(center = vc)

    def recreate_item(self, w=None, obj_group=None):
        c = obj_group.cobj['opes'][-1].content
        if obj_group.cobj['type'] == Annotation:
            # t : content a parse
            # b : content a parse
            # d : content a parse
            t=None
            b=d=0
            t = self.controller.package.get_element_by_id(obj_group.cobj['cid'])
            if t is None or not isinstance(t, AnnotationType):
                print "No corresponding type, creation aborted"
                return
            a = int(c.find("begin=")+6)
            aa = int(c.find("\n", a))
            b = long(c[a:aa])
            a = int(c.find("end=")+4)
            aa = int(c.find("\n", a))
            e = long(c[a:aa])
            d = e-b
            a = int(c.find("content=")+9)
            aa = len(c)-1
            cont = c[a:aa]
            an = self.controller.package.createAnnotation(
                ident=obj_group.cobj['id'],
                type=t,
                author=config.data.userid,
                date=self.controller.get_timestamp(),
                fragment=MillisecondFragment(begin=b,
                                             duration=d))
            an.content.data = urllib.unquote(cont.encode('utf-8'))
            self.controller.package.annotations.append(an)
            self.controller.notify("AnnotationCreate", annotation=an, comment="Recreated from Trace")
        elif obj_group.cobj['type'] == Relation:
            print 'todo'
        else:
            print 'TODO'
        
        return
    
    def edit_item(self, w=None, obj=None):
        if obj is not None:
            self.controller.gui.edit_element(obj)
        
    def goto(self, w=None, time=None):
        c=self.controller
        pos = c.create_position (value=time,
                                     key=c.player.MediaTime,
                                     origin=c.player.AbsolutePosition)
        c.update_status (status="set", position=pos)
        return
        
    def canvas_release(self, w, t, ev):
        if ev.state & gtk.gdk.SHIFT_MASK:
            self.selection[2]=ev.x
            self.selection[3]=ev.y
            if self.sel_frame:
                self.sel_frame.remove()
                self.sel_frame=None
            self.widget.get_parent_window().set_cursor(None)
            min_y=min(self.selection[1], self.selection[3])
            max_y=max(self.selection[1], self.selection[3])
            h = self.canvas.get_allocation().height
            va=self.sw.get_vadjustment()
            if max_y-min_y<=3:
                #must be a misclick
                return
            rapp = (max_y - min_y) / h
            vc = self.timefactor * ((min_y + max_y) / 2.0) * (va.upper / self.canvasY)
            self.timefactor = rapp * self.timefactor
            self.canvasY = rapp * self.canvasY
            self.obj_l = rapp * self.obj_l
            self.canvas.set_bounds (0,0,self.canvasX,self.canvasY)
            self.refresh(center = vc)
            self.selection = [ 0, 0, 0, 0]
            return
        
    def canvas_clicked(self, w, t, ev):
        if ev.state & gtk.gdk.SHIFT_MASK:
            self.selection = [ ev.x, ev.y, 0, 0]
            if self.sel_frame:
                self.sel_frame.remove()
                self.sel_frame=None
            self.widget.get_parent_window().set_cursor(gtk.gdk.Cursor(gtk.gdk.PLUS))
            return
        obj_gp = None
        evt_gp = None
        l = self.canvas.get_items_at(ev.x, ev.y, False)
        if l is not None:
            for o in l:
                go = o.get_parent()
                if isinstance(go, ObjGroup):
                    obj_gp = go
                if isinstance(go, EventGroup):
                    evt_gp = go
        if obj_gp is None and evt_gp is None:
            return
        if ev.button == 3:
            #clic droit sur un item
            menu=gtk.Menu()
            if obj_gp is not None:
                i=gtk.MenuItem(_("Zoom and center on linked items"))
                i.connect("activate", self.zoom_on, obj_gp)
                menu.append(i)
                obj = objt = None
                if obj_gp.cobj['id'] is not None:   
                    obj = self.controller.package.get_element_by_id(obj_gp.cobj['id'])
                if obj_gp.cobj['cid'] is not None:      
                    objt = self.controller.package.get_element_by_id(obj_gp.cobj['cid'])
                if obj is not None:
                    i=gtk.MenuItem(_("Edit item"))
                    i.connect("activate", self.edit_item, obj)
                    menu.append(i)
                elif objt is not None:
                    i=gtk.MenuItem(_("Recreate item"))
                    i.connect("activate", self.recreate_item, obj_gp)
                    menu.append(i)
                m = gtk.Menu()
                mt= []
                for op in obj_gp.cobj['opes']:
                    if op.movietime not in mt:
                        n=''
                        if op.name in INCOMPLETE_OPERATIONS_NAMES:
                            n = INCOMPLETE_OPERATIONS_NAMES[op.name]
                        else:
                            n = ECACatalog.event_names[op.name]
                        mt.append(op.movietime)
                        i = gtk.MenuItem("%s (%s)" % (time.strftime("%H:%M:%S", time.gmtime(op.movietime/1000)), n))
                        i.connect("activate", self.goto, op.movietime)
                        m.append(i)
                i=gtk.MenuItem(_("Go to..."))
                i.set_submenu(m)
                menu.append(i)
            if evt_gp is not None:
                i=gtk.MenuItem(_("Zoom on action"))
                i.connect("activate", self.zoom_on, evt_gp)
                menu.append(i)
                if obj_gp is None:
                    m = gtk.Menu()
                    mt= []
                    for op in evt_gp.event.operations:
                        if op.movietime not in mt:
                            n=''
                            if op.name in INCOMPLETE_OPERATIONS_NAMES:
                                n = INCOMPLETE_OPERATIONS_NAMES[op.name]
                            else:
                                n = ECACatalog.event_names[op.name]
                            mt.append(op.movietime)
                            i = gtk.MenuItem("%s (%s)" % (time.strftime("%H:%M:%S", time.gmtime(op.movietime/1000)), n))
                            i.connect("activate", self.goto, op.movietime)
                            m.append(i)
                    i=gtk.MenuItem(_("Go to..."))
                    i.set_submenu(m)
                    menu.append(i)
            menu.show_all()
            menu.popup(None, None, None, ev.button, ev.time)
        elif ev.button == 1:
            if obj_gp is not None:
                self.toggle_lock(w=obj_gp)
            else:
                self.toggle_lock(w=evt_gp)

    def toggle_lock(self, w=None):
        self.links_locked = not self.links_locked
        if self.links_locked:
            #self.btnl.set_label(_('Locked'))
            img = self.btnl.get_icon_widget()
            img.set_from_file(config.data.advenefile( ( 'pixmaps', 'locked.png') ))
            img.show()
            self.btnl.set_icon_widget(img)
        else:
            #self.btnl.set_label(_('Unlocked'))
            img = self.btnl.get_icon_widget()
            img.set_from_file(config.data.advenefile( ( 'pixmaps', 'unlocked.png') ))
            img.show()
            self.btnl.set_icon_widget(img)
        i=0
        root = self.canvas.get_root_item()
        while i < root.get_n_children():
            go = root.get_child(i)
            if isinstance(go, ObjGroup) or isinstance(go, EventGroup):
                if self.links_locked:
                    #print "lock %s" % go
                    go.handler_block(go.handler_ids['enter-notify-event'])
                    go.handler_block(go.handler_ids['leave-notify-event'])
                else:
                    #print "unlock %s" % go
                    go.handler_unblock(go.handler_ids['enter-notify-event'])
                    go.handler_unblock(go.handler_ids['leave-notify-event'])
                    # if selected group, force leave
                    if hasattr(go, 'center_sel') and go.center_sel:
                        go.on_mouse_leave(None, None, None)
                    if go == w:
                        go.on_mouse_over(None, None, None)
            i+=1

    def draw_marks(self):
        # verifying start time (changed if an import occured)
        self.start_time = self.active_trace.levels['events'][0].time
        # adding time lines
        wa = self.canvas.get_parent().get_allocation().height
        tinc = 60
        if wa > 100:
            tinc = wa/4.0 # 4 marks in the widget
        else:
            tinc = 60000 / self.timefactor
        t=tinc
        #print t, wa
        ld = goocanvas.LineDash([5.0, 20.0])
        #time.localtime(t*self.timefactor/1000)
        #time.gmtime(t*self.timefactor/1000)
        while t < self.canvasY:
            #print t
            goocanvas.polyline_new_line(self.canvas.get_root_item(),
                                        0,
                                        t,
                                        self.canvasX,
                                        t,
                                        line_dash=ld,
                                        line_width = 0.2)
            goocanvas.Text(parent = self.canvas.get_root_item(),
                        text = time.strftime("%H:%M:%S",time.localtime(self.start_time+t*self.timefactor/1000)),
                        x = 0,
                        y = t-5,
                        width = -1,
                        anchor = gtk.ANCHOR_W,
                        fill_color_rgba=0x121212FF, #0x23456788
                        font = "Sans 7")
            goocanvas.Text(parent = self.canvas.get_root_item(),
                        text = time.strftime("%H:%M:%S",time.localtime(self.start_time+t*self.timefactor/1000)),
                        x = self.canvasX-4,
                        y = t-5,
                        width = -1,
                        fill_color_rgba=0x121212FF,
                        anchor = gtk.ANCHOR_E,
                        font = "Sans 7")
            t += tinc
        return

    def redraw_head_canvas(self):
        root = self.head_canvas.get_root_item()
        while root.get_n_children()>0:
            root.remove_child (0)
        self.populate_head_canvas()
        return

    def populate_head_canvas(self):
        offset = 0
        #colors = [0x000088AA, 0x0000FFAA, 0x008800AA, 0x00FF00AA, 0x880000AA, 0xFF0000FF, 0x008888FF, 0x880088FF, 0x888800FF, 0xFF00FFFF, 0x00FFFFFF, 0xFFFF00FF, 0x00FF88FF, 0xFF0088FF, 0x0088FFFF, 0x8800FFFF, 0x88FF00FF, 0xFF8800FF]
        # 18 col max
        for c in ACTIONS:
            etgroup = HeadGroup(self.controller, self.head_canvas, c, (self.colspacing+self.col_width)*offset, 0, self.col_width, 8, ACTION_COLORS[offset])
            self.cols[c]=(etgroup, None)
            offset += 1
        return

    def destroy(self, source=None, event=None):
        self.tracer.unregister_view(self)
        return False

    def refresh(self, action=None, center = None):
        # method to refresh the canvas display
        # 1/ clean the canvas, memorizing selected item
        # 2/ recalculate the canvas area according to timefactor and last action
        # 3/ redraw time separators
        # 4/ redraw each action
        # 5/ recenter the canvas according to previous centering
        # 6/ reselect selected item
        # 7/ re-deactive locked_links
        # action : the new action forcing a refresh (if action couldnt be displayed in the current canvas area)
        # center : the timestamp on which the display needs to be centered
        root = self.canvas.get_root_item()
        selected_item = None
        while root.get_n_children()>0:
            #print "refresh removing %s" % root.get_child (0)
            c = root.get_child(0)
            if isinstance(c, EventGroup):
                for k in c.objs.keys():
                    if c.objs[k][0] is not None:
                        if c.objs[k][0].center_sel:
                            selected_item = (c.event, k)
            c.remove()
        for act in self.cols.keys():
            (h,l) = self.cols[act]
            self.cols[act] = (h, None)
        if not ('actions' in self.active_trace.levels.keys() and self.active_trace.levels['actions']):
            return
        a = self.active_trace.levels['actions'][-1].activity_time[1]
        #if action and a< action.activity_time[1]:
        #    a = action.activity_time[1]
        for act in self.active_trace.levels['actions']:
            if act.activity_time[1]>a:
                a=act.activity_time[1]
            #print "t1 %s Ytf %s" % (a, self.canvasY*self.timefactor)
        if a<(self.canvasY-self.incr)*self.timefactor or a>self.canvasY*self.timefactor:
            self.canvasY = int(1.0*a/self.timefactor + 1)
        #print self.canvasX, self.canvasY
        self.canvas.set_bounds (0, 0, self.canvasX, self.canvasY)
        #print "%s %s" % (self.timefactor, self.canvasY)
        self.canvas.show()
        self.draw_marks()
        sel_eg = None
        for i in self.active_trace.levels['actions']:
            ev = self.receive_int(self.active_trace, action=i)
            if selected_item is not None and i == selected_item[0]:
                sel_eg = ev
            #if action is not None and action ==i:
            #    break
        if center:
            va=self.sw.get_vadjustment()
            va.value = center/self.timefactor-va.page_size/2.0
            if va.value<va.lower:
                va.value=va.lower
            elif va.value>va.upper-va.page_size:
                va.value=va.upper-va.page_size
        if selected_item is not None:
            #print "sel item : %s %s" % selected_item
            if sel_eg is not None:
                if sel_eg.get_canvas() is None:
                    #print "group deprecated"
                    # group deprecated, need to find the new one (happens when refreshing during a receive
                    n=0
                    while n<root.get_n_children():
                        #print "refresh removing %s" % root.get_child (0)
                        c = root.get_child(n)
                        if isinstance(c, EventGroup):
                            if c.event == selected_item[0]:
                                # that's the good action
                                sel_eg = c
                        n += 1
                if sel_eg.objs is not None:
                    if sel_eg.objs[selected_item[1]] is not None:
                        if sel_eg.objs[selected_item[1]][0] is not None:
                            sel_eg.objs[selected_item[1]][0].toggle_rels()
        if self.links_locked:
            i=0
            root = self.canvas.get_root_item()
            while i < root.get_n_children():
                go = root.get_child(i)
                if isinstance(go, ObjGroup) or isinstance(go, EventGroup):
                    go.handler_block(go.handler_ids['enter-notify-event'])
                    go.handler_block(go.handler_ids['leave-notify-event'])
                i+=1
        return


    def receive(self, trace, event=None, operation=None, action=None):
        # trace : the full trace to be managed
        # event : the new or latest modified event
        # operation : the new or latest modified operation
        # action : the new or latest modified action
        # return False.
        # This function is called by the tracer to update the gui
        # it should always return False to avoid 100% cpu consumption.
        if self.active_trace == trace:
            self.receive_int(trace, event, operation, action)
        if not (event or operation or action):
            tm = self.trace_selector.get_model()
            n=len(tm)
            if n < len(self.tracer.traces):
                tm.append((_("%(name)s (%(index)s)") % {
                        'name': self.tracer.traces[n].name, 
                        'index': n}, 
                           n, None ))
        return False


    def receive_int(self, trace, event=None, operation=None, action=None):
        # trace : the full trace to be managed
        # event : the new or latest modified event
        # operation : the new or latest modified operation
        # action : the new or latest modified action
        # return the created group
        #print "received : action %s, operation %s, event %s" % (action, operation, event)
        ev = None
        if event and (event.name=='DurationUpdate' or event.name=='MediaChange'):
            self.docgroup.changeMovielength(trace)
        if operation:
            self.docgroup.addLine(operation.movietime)
        if (operation or event) and action is None:
            return ev
        if action is None:
            #redraw screen
            self.refresh()
            self.docgroup.redraw(trace)
            #if self.autoscroll:
            #    a = self.sw.get_vadjustment()
            #    a.value=a.upper-a.page_size
            return ev
        h,l = self.cols[action.name]
        color = h.color_c
        if l and l.event == action:
            ev = l
            y1=l.rect.get_bounds().y1+1
            x1=l.rect.get_bounds().x1+1
            #print "receive removing %s" % l.rect
            #child_num = l.find_child (l.rect)
            #if child_num>=0:
            #    l.remove_child (child_num)
            l.rect.remove()
            length = (action.activity_time[1]-action.activity_time[0])//self.timefactor
            if y1+length > self.canvasY:
                self.refresh(action)
                return ev
            else:
                l.x = x1
                l.y = y1
                l.l = length
                l.rect = l.newRect(l.color, l.color_c)
                l.redrawObjs(self.obj_l)
        else:
            x = h.rect.get_bounds().x1+1
            y = action.activity_time[0]//self.timefactor
            length = (action.activity_time[1]-action.activity_time[0])//self.timefactor
            #print "%s %s %s %s" % (action, x, y, length)
            if action.activity_time[1] > self.canvasY*self.timefactor:
                #print "%s %s %s" % (action.name , action.activity_time[1], self.canvasY*self.timefactor)
                self.refresh(action)
                return ev
            else:
                ev = EventGroup(self.link_mode, self.controller, self.inspector, self.canvas, self.docgroup, None, action, x, y, length, self.col_width, self.obj_l, 14, color, self.links_locked)
                self.cols[action.name]=(h,ev)
            #self.lasty = ev.rect.get_bounds().y2
            #print "%s %s %s" % (y, length, self.lasty)
        if self.autoscroll:
            a = self.sw.get_vadjustment()
            a.value=a.upper-a.page_size
        #redraw canvasdoc
        #self.docgroup.redraw(trace)
        #if 'actions' in self.tracer.trace.levels.keys() and self.tracer.trace.levels['actions']:
        return ev

class HeadGroup (Group):
    def __init__(self, controller=None, canvas=None, name="N/A", x = 5, y=0, w=90, fontsize=14, color_c=0x00ffff50):
        Group.__init__(self, parent = canvas.get_root_item ())
        self.controller=controller
        self.name=name[0:2]
        self.rect = None
        self.text = None
        self.w = 90
        self.color_s = "black"
        self.color_c = color_c
        self.fontsize=fontsize
        self.rect = goocanvas.Rect (parent = self,
                                    x = x,
                                    y = y,
                                    width = self.w,
                                    height = 20,
                                    fill_color_rgba = 0xFFFFFF00,
                                    stroke_color = 0xFFFFFF00,
                                    line_width = 0)
        self.text = goocanvas.Text (parent = self,
                                        text = self.name,
                                        x = x+w/2,
                                        y = y+15,
                                        width = -1,
                                        anchor = gtk.ANCHOR_CENTER,
                                        font = "Sans Bold %s" % str(self.fontsize))

        def change_name(self, name):
            return

        def change_font(self, font):
            return

class EventGroup (Group):
    def __init__(self, link_mode=0, controller=None, inspector=None, canvas=None, dg=None, type=None, event=None, x =0, y=0, l=1, w=90, ol=5, fontsize=6, color_c=0x00ffffff, blocked=False):
        Group.__init__(self, parent = canvas.get_root_item ())
        self.canvas = canvas
        self.controller=controller
        self.inspector = inspector
        self.event=event
        self.type=type
        self.link_mode=link_mode
        self.commentMark = None
        self.dg = dg
        self.rect = None
        self.color_sel = 0xD9D919FF
        self.color_c = color_c
        self.color_o = 0xADEAEAFF
        self.color_m = 0x00ffbfff
        self.color = "black"
        self.fontsize=fontsize
        self.x = x
        self.y= y
        self.l = l
        self.ol = ol
        self.w = w
        self.rect = self.newRect (self.color, self.color_c)
        self.objs={}
        #self.lines = []
        self.redrawObjs(ol, blocked)
        self.handler_ids = {
        'enter-notify-event':None,
        'leave-notify-event':None,
        }
        #self.connect('button-press-event', self.on_click)
        self.handler_ids['enter-notify-event'] = self.connect('enter-notify-event', self.on_mouse_over)
        self.handler_ids['leave-notify-event'] = self.connect('leave-notify-event', self.on_mouse_leave)
        if blocked:
            self.handler_block(self.handler_ids['enter-notify-event'])
            self.handler_block(self.handler_ids['leave-notify-event'])
        if self.event.comment!='':
            self.addCommentMark()
            
    def newRect(self, color, color_c):
        return goocanvas.Rect (parent = self,
                                    x = self.x,
                                    y = self.y,
                                    width = self.w,
                                    height = self.l,
                                    fill_color_rgba = color_c,
                                    stroke_color = color,
                                    line_width = 2.0)

    def addObj(self, obj_id, xx, yy, ol, color, color_o, blocked):
        (pds, cobj) = self.objs[obj_id][1:5]
        return ObjGroup(self.link_mode, self.controller, self.inspector, self.canvas, self.dg, xx, yy, ol, self.fontsize, pds, cobj, blocked)

    def redrawObjs(self, ol=5, blocked=False):
        #FIXME : brutal way to do that. Need only to find what operation was added to update only this square
        for obj in self.objs.keys():
            obg = self.objs[obj][0]
            if obg is not None:
                #print "redrawObjs removing %s" % r_obj
                #child_num = self.find_child (obg)
                #if child_num>=0:
                #    self.remove_child (child_num)
                obg.remove()
        self.objs = {}
        for op in self.event.operations:
            obj = op.concerned_object['id']
            if obj is None:
                continue
            if obj in self.objs.keys():
                (pds, cobj) = self.objs[obj][1:5]
                cobj['opes'].append(op)
                self.objs[obj] = (None, pds+1, cobj)
            else:
                cobj = op.concerned_object
                cobj['opes'] = [op]
                self.objs[obj] = (None, 1, cobj)
            #print "obj %s opes %s" % (obj, obj_opes)
        #self.objs : item : #time modified during action
        y=self.rect.get_bounds().y1+1
        x=self.rect.get_bounds().x1+1
        ox = x+2
        oy = y+2
        l = self.rect.props.height
        w = self.rect.props.width
        nb = len(self.objs.keys())
        ol = w/3 - 4
        while (floor(((w-3)/(ol+2)))*floor(((l-3)/(ol+2)))< nb and ol>3):
            ol-=1
        #print "w:%s l:%s nb:%s nbw:%s nbl:%s ol:%s" % (w-2, l-2, nb, floor(((w-2)/(ol+2))), floor(((l-2)/(ol+2))), ol)
        if ol > l-4:
            if l>7:
                ol=l-4
            else:
                return
        if ol > 20:
            ol=20
        # need to fix fontsize according to object length with a min of 6 and a max of ??,
        self.fontsize = ol-1
        for obj in self.objs.keys():
            #print "ox %s oy %s ol %s w %s l %s" % (ox, oy, ol, w+x, l+y)
            if ox+(ol+2)>= x+w:
                if oy+(ol+2)*2>= y+l:
                    ox = x+2
                    oy += (ol+1)
                    #FIXME
                    goocanvas.Text(parent = self,
                                        text = "...",
                                        x = ox,
                                        y = oy,
                                        width = -1,
                                        anchor = gtk.ANCHOR_NORTH_WEST,
                                        font = "Sans Bold %s" % self.fontsize)
                    break
                else:
                    ox = x+2
                    oy += (ol+2)
                    (pds, cobj) = self.objs[obj][1:5]
                    self.objs[obj]= (self.addObj(obj, ox+ol/2.0, oy+ol/2.0, ol/2.0, self.color, self.color_o, blocked), pds, cobj)
                    ox += (ol+2)
            else:
                (pds, cobj) = self.objs[obj][1:5]
                self.objs[obj]= (self.addObj(obj, ox+ol/2.0, oy+ol/2.0, ol/2.0, self.color, self.color_o, blocked), pds, cobj)
                ox += (ol+2)
            #print "ox %s oy %s ol %s w %s l %s" % (ox, oy, ol, w+x, l+y)

    def on_mouse_over(self, w, target, event):
        #print '1 %s %s %s %s' % self.canvas.get_bounds()
        self.fill_inspector()
        self.dg.changeMarks(action=self.event)
        #print '2 %s %s %s %s' % self.canvas.get_bounds()
        return

    def on_mouse_leave(self, w, target, event):
        self.clean_inspector()
        self.dg.changeMarks()
        return

    def clean_inspector(self):
        self.inspector.clean()

    def fill_inspector(self):
        self.inspector.fillWithAction(self)
        
    def removeCommentMark(self):
        if self.commentMark:
            self.commentMark.remove()
        self.commentMark = None
    
    def addCommentMark(self):
        if self.commentMark:
            return
        self.commentMark = goocanvas.Rect (parent = self,
                                    x = self.x+self.w-5,
                                    y = self.y+self.l-5,
                                    width = 5,
                                    height = 5,
                                    fill_color_rgba = self.color_m,
                                    stroke_color = self.color_m,
                                    line_width = 2.0)


class ObjGroup (Group):
    def __init__(self, link_mode=0, controller=None, inspector=None, canvas=None, dg=None, x=0, y=0, r=4, fontsize=6, pds=1, obj=None, blocked=False):
        Group.__init__(self, parent = canvas.get_root_item ())
        self.controller=controller
        self.rep = None
        self.text = None
        self.canvas = canvas
        self.dg=dg
        self.link_mode=link_mode
        self.inspector = inspector
        self.color_sel = 0xD9D919FF
        self.stroke_color_sel = "red"
        self.color_f = 0xFFFFFFFF
        self.color_s = "black"
        self.fontsize = 5
        self.poids = pds
        self.cobj = obj
        self.x = x
        self.y = y
        self.r = r
        # trying to get the item color in advene
        temp_it = self.controller.package.get_element_by_id(self.cobj['id'])
        temp_c = self.controller.get_element_color(temp_it)
        if temp_c is not None:
            if len(temp_c)==7:
                self.color_f= int(temp_c[1:]+"FF", 16)
            elif len(temp_c)==13:
                b1=int(temp_c[1:5], 16)/0x101
                b2=int(temp_c[5:9], 16)/0x101
                b3=int(temp_c[9:], 16)/0x101
                self.color_f= b1*0x1000000 + b2*0x10000 + b3*0x100 + 0xFF
                #print self.color_f

        self.rep = self.newRep()
        self.text = self.newText()
        self.lines = []
        self.sel = False
        self.center_sel = False
        self.handler_ids = {
        'enter-notify-event':None,
        'leave-notify-event':None,
        }
        self.handler_ids['enter-notify-event'] = self.connect('enter-notify-event', self.on_mouse_over)
        self.handler_ids['leave-notify-event'] = self.connect('leave-notify-event', self.on_mouse_leave)
        if blocked:
            self.handler_block(self.handler_ids['enter-notify-event'])
            self.handler_block(self.handler_ids['leave-notify-event'])

    def on_mouse_over(self, w, target, event):
        self.toggle_rels()
        self.fill_inspector()
        self.dg.changeMarks(obj=self)
        return

    def on_mouse_leave(self, w, target, event):
        self.toggle_rels()
        self.clean_inspector()
        self.dg.changeMarks()
        return

    def clean_inspector(self):
        self.inspector.clean()

    def fill_inspector(self):
        self.inspector.fillWithItem(self)

    #~ def get_link_mode(self):
        
        #~ return 0

    def toggle_rels(self):
        r = self.canvas.get_root_item()
        chd = []
        i = 0
        desel = False
        while i <r.get_n_children():
            f = r.get_child(i)
            if isinstance(f, EventGroup) and f.objs is not None:
                chd.append(f)
                for obj_id in f.objs.keys():
                    obg = f.objs[obj_id][0]
                    if obg is None:
                        continue
                    for l in obg.lines:
                        #n=obg.find_child(l)
                        #if n>=0:
                        #    obg.remove_child(n)
                        l.remove()
                    obg.lines=[]
                    if obg.sel:
                        if obg.center_sel and obg == self:
                            desel = True
                        obg.deselect()
            i+=1
        if desel:
            return
        self.select()
        self.center_sel = True
        if self.link_mode == 0:
            for c in chd:
                if self.cobj['id'] in c.objs.keys():
                    obj_gr = c.objs[self.cobj['id']][0]
                    if obj_gr != self:
                        x2=y2=0
                        x1 = self.x
                        y1 = self.y
                        if obj_gr is None:
                            x2 = c.rect.get_bounds().x1 + c.rect.props.width/2
                            y2 = c.rect.get_bounds().y1 + c.rect.props.height/2
                        else:
                            x2 = obj_gr.x
                            y2 = obj_gr.y
                            obj_gr.select()
                        p = goocanvas.Points ([(x1, y1), (x2,y2)])
                        self.lines.append(goocanvas.Polyline (parent = self,
                                        close_path = False,
                                        points = p,
                                        stroke_color = 0xFFFFFFFF,
                                        line_width = 1.0,
                                        start_arrow = False,
                                        end_arrow = False,
                                        ))
        else:
            dic={}
            for c in chd:
                if self.cobj['id'] in c.objs.keys():
                    obj_gr = c.objs[self.cobj['id']][0]
                    obj_time = c.objs[self.cobj['id']][2]['opes'][0].time
                    if obj_gr is None:
                        x = c.rect.get_bounds().x1 + c.rect.props.width/2
                        y = c.rect.get_bounds().y1 + c.rect.props.height/2
                    else:
                        x = obj_gr.x
                        y = obj_gr.y
                        obj_gr.select()                    
                    dic[obj_time]= (x, y)
            ks = dic.keys()
            ks.sort()
            lp = []
            for key in ks:
                lp.append(dic[key])
            p=goocanvas.Points(lp)
            self.lines.append(goocanvas.Polyline (parent = self,
                                        close_path = False,
                                        points = p,
                                        stroke_color = 0xFFFFFFFF,
                                        line_width = 1.0,
                                        start_arrow = False,
                                        end_arrow = False,
                                        ))
                
        return

    def select(self):
        self.rep.props.fill_color_rgba=self.color_sel
        self.rep.props.stroke_color = self.stroke_color_sel
        self.sel = True

    def deselect(self):
        self.rep.props.fill_color_rgba=self.color_f
        self.rep.props.stroke_color = self.color_s
        self.sel = False
        self.center_sel = False

    def newRep(self):
        return goocanvas.Ellipse(parent=self,
                        center_x=self.x,
                        center_y=self.y,
                        radius_x=self.r,
                        radius_y=self.r,
                        stroke_color=self.color_s,
                        fill_color_rgba=self.color_f,
                        line_width=1.0)

    def newText(self):
    #
    #
    #
        
        txt = 'U'
        if self.cobj['type'] is None:
            # need to test if we can find the type in an other way, use of type() is not a good thing
            o = self.controller.package.get_element_by_id(self.cobj['id'])
            self.cobj['type']=type(o)
            #print self.type
        if self.cobj['type'] == Schema:
            txt = 'S'
        elif self.cobj['type'] == AnnotationType:
            txt = 'AT'
        elif self.cobj['type'] == RelationType:
            txt = 'RT'
        elif self.cobj['type'] == Annotation:
            txt = 'A'
        elif self.cobj['type'] == Relation:
            txt = 'R'
        elif self.cobj['type'] == View:
            txt = 'V'
        else:
            print "type inconnu: %s" % self.cobj['type']
        return goocanvas.Text (parent = self,
                        text = txt,
                        x = self.x,
                        y = self.y,
                        width = -1,
                        anchor = gtk.ANCHOR_CENTER,
                        font = "Sans %s" % str(self.fontsize))


class Inspector (gtk.VBox):
#
# Inspector component to display informations concerning items and actions in the timeline
#
    
    def __init__ (self, controller=None):
        gtk.VBox.__init__(self)
        self.action=None
        self.controller=controller
        self.pack_start(gtk.Label(_('Inspector')), expand=False)
        self.pack_start(gtk.HSeparator(), expand=False)
        self.inspector_id = gtk.Label('')
        self.pack_start(self.inspector_id, expand=False)
        self.inspector_id.set_alignment(0, 0.5)
        self.inspector_id.set_tooltip_text(_('Item Id'))
        self.inspector_type = gtk.Label('')
        self.pack_start(self.inspector_type, expand=False)
        self.inspector_type.set_tooltip_text(_('Item name or class'))
        self.inspector_type.set_alignment(0, 0.5)
        self.inspector_name = gtk.Label('')
        self.pack_start(self.inspector_name, expand=False)
        self.inspector_name.set_tooltip_text(_('Type or schema'))
        self.inspector_name.set_alignment(0, 0.5)
        self.pack_start(gtk.HSeparator(), expand=False)
        self.pack_start(gtk.Label(_('Operations')), expand=False)
        self.pack_start(gtk.HSeparator(), expand=False)
        opscwin = gtk.ScrolledWindow ()
        opscwin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        opscwin.set_border_width(0)
        self.inspector_opes= gtk.VBox()
        opscwin.add_with_viewport(self.inspector_opes)
        self.pack_start(opscwin, expand=True)
        self.commentBox = gtk.VBox()
        self.comment=gtk.Entry()
        save_btn=gtk.Button(_('Save'))
        def save_clicked(w):
            if self.action:
                self.action.event.change_comment(self.comment.get_text())
                if self.comment.get_text()!='':
                    self.action.addCommentMark()
                else:
                    self.action.removeCommentMark()
            
        save_btn.connect('clicked', save_clicked)
        clear_btn=gtk.Button(_('Clear'))
        def clear_clicked(w):
            self.comment.set_text('')
            save_clicked(w)
            
        clear_btn.connect('clicked', clear_clicked)
        btns = gtk.HBox()
        btns.pack_start(save_btn, expand=False)
        btns.pack_start(clear_btn, expand=False)
        self.commentBox.pack_end(btns, expand=False)
        self.commentBox.pack_end(self.comment, expand=False)
        self.commentBox.pack_end(gtk.HSeparator(), expand=False)
        self.commentBox.pack_end(gtk.Label(_('Comment')), expand=False)
        self.commentBox.pack_end(gtk.HSeparator(), expand=False)
        self.pack_end(self.commentBox, expand=False)
        self.clean()

    def fillWithItem(self, item):
    #
    # Fill the inspector with informations concerning an object
    # item : the advene object to display
    
        if item.cobj['id'] is not None:
            self.inspector_id.set_text(item.cobj['id'])
        if item.cobj['cid'] is not None:
            self.inspector_name.set_text(item.cobj['cid'])
        if item.cobj['name'] is not None:
            self.inspector_type.set_text(item.cobj['name'])
        self.addOperations(item.cobj['opes'])
        self.show_all()

    def fillWithAction(self, action):
    #
    # Fill the inspector with informations concerning an action
    # action : the action to display
    
        self.action=action
        self.inspector_id.set_text(_('Action'))
        self.inspector_name.set_text('')
        self.inspector_type.set_text(action.event.name)
        self.pack_end(self.commentBox, expand=False)
        self.comment.set_text(action.event.comment)
        self.addOperations(action.event.operations)
        self.show_all()

    def addOperations(self, op_list):
    #
    # used to pack operation boxes in the inspector 
    # op_list : list of operations to display
        for c in self.inspector_opes.get_children():
            self.inspector_opes.remove(c)
        for o in op_list:
            l = self.addOperation(o)
            l.set_size_request(-1, 25)
            self.inspector_opes.pack_start(l, expand=False)


    def addOperation(self, obj_evt):
    #
    # used to build a box to display an operation 
    # obj_evt : operation to build a box for

        corpsstr = ''
        if obj_evt.content is not None:
            corpsstr = urllib.unquote(obj_evt.content.encode('utf-8'))
        ev_time = time.strftime("%H:%M:%S", time.localtime(obj_evt.time))
        #ev_time = helper.format_time(obj_evt.activity_time)
        if obj_evt.name in INCOMPLETE_OPERATIONS_NAMES:
            n = INCOMPLETE_OPERATIONS_NAMES[obj_evt.name]
        else:
            n = ECACatalog.event_names[obj_evt.name]
        entetestr = "%s : %s" % (ev_time, n)
        if obj_evt.concerned_object['id']:
            entetestr = entetestr + ' (%s)' % obj_evt.concerned_object['id']
        elif obj_evt.name=='PlayerSet':
            # destination time to add
            entetestr = entetestr + ' %s' % obj_evt.content
        entete = gtk.Label(entetestr.encode("UTF-8"))
        hb = gtk.HBox()
        box = gtk.EventBox()
        tr = TimestampRepresentation(obj_evt.movietime, self.controller, 20, 0, None , False)
        if tr is not None:
            hb.pack_start(tr, expand=False)
            hb.pack_start(gtk.VSeparator(), expand=False)
        if corpsstr != "":
            box.set_tooltip_text(corpsstr)
        def box_pressed(w, event, id):
            if event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
                if id is not None:
                    obj = self.controller.package.get_element_by_id(id)
                    if obj is not None:
                        self.controller.gui.edit_element(obj)
                    else:
                        print "item %s no longuer exists" % id
            return
        box.add(entete)
        box.connect('button-press-event', box_pressed, obj_evt.concerned_object['id'])
        hb.pack_start(box, expand=False)
        return hb

    def clean(self):
    #
    # used to clean the inspector when selecting no item
    #
        self.action=None
        self.inspector_id.set_text('')
        self.inspector_name.set_text('')
        self.inspector_type.set_text('')
        self.remove(self.commentBox)
        for c in self.inspector_opes.get_children():
            self.inspector_opes.remove(c)
        self.comment.set_text('')
        self.show_all()

class DocGroup (Group):
    def __init__(self, controller=None, canvas=None, name="N/A", x =10, y=10, w=80, h=20, fontsize=14, color_c=0x00000050):
        Group.__init__(self, parent = canvas.get_root_item ())
        self.controller=controller
        self.canvas=canvas
        self.name=name
        self.rect = None
        self.w = w
        self.h = h
        self.x= x
        self.y = y
        self.movielength = 1
        if self.controller.package.cached_duration>0:
            self.movielength = self.controller.package.cached_duration
        self.color_c = color_c
        self.color_f = 0xFFFFFF00
        self.lw = 1.0
        self.fontsize=fontsize
        self.lines=[]
        self.marks=[]
        self.rect = self.newRect()
        self.timemarks=[]
        self.connect('button-press-event', self.docgroup_clicked)

    def newRect(self):
        return goocanvas.Rect (parent = self,
                                    x = self.x,
                                    y = self.y,
                                    width = self.w,
                                    height = self.h,
                                    fill_color_rgba = self.color_f,
                                    stroke_color_rgba = self.color_c,
                                    line_width = self.lw)

    def drawtimemarks(self):
        nbmax = self.w / 10
        if nbmax > 3:
            nbmax = 3
        #timestamp 0
        self.timemarks.append(goocanvas.Text (parent = self,
                                text = time.strftime("%H:%M:%S", time.gmtime(0)),
                                x = self.x,
                                y = self.y+self.h+7,
                                fill_color = self.color_c,
                                width = -1,
                                anchor = gtk.ANCHOR_CENTER,
                                font = "Sans 6"))
        p = goocanvas.Points ([(self.x, self.y+self.h), (self.x, self.y+self.h+2)])
        self.timemarks.append(goocanvas.Polyline (parent = self,
                                        close_path = False,
                                        points = p,
                                        stroke_color_rgba = self.color_c,
                                        line_width = 1.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        ))
        #timestamp fin
        self.timemarks.append(goocanvas.Text (parent = self,
                                text = time.strftime("%H:%M:%S", time.gmtime(self.movielength/1000)),
                                x = self.x+self.w,
                                y = self.y+self.h+7,
                                fill_color = self.color_c,
                                width = -1,
                                anchor = gtk.ANCHOR_CENTER,
                                font = "Sans 6"))
        p = goocanvas.Points ([(self.x+self.w, self.y+self.h), (self.x+self.w, self.y+self.h+2)])
        self.timemarks.append(goocanvas.Polyline (parent = self,
                                        close_path = False,
                                        points = p,
                                        stroke_color_rgba = self.color_c,
                                        line_width = 1.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        ))
        if nbmax <=0:
            return
        sec = self.movielength / 1000
        if sec < nbmax:
            return
        #1-3 timestamps intermediaires
        for i in range(0, nbmax+1):
            rap = 1.0 * i / (nbmax+1)
            self.timemarks.append(goocanvas.Text (parent = self,
                                text = time.strftime("%H:%M:%S", time.gmtime(sec * rap)),
                                x = self.x + self.w * rap,
                                y = self.y+self.h+7,
                                fill_color = self.color_c,
                                width = -1,
                                anchor = gtk.ANCHOR_CENTER,
                                font = "Sans 6"))
            p = goocanvas.Points ([(self.x + self.w * rap, self.y+self.h), (self.x + self.w * rap, self.y+self.h+2)])
            self.timemarks.append(goocanvas.Polyline (parent = self,
                                        close_path = False,
                                        points = p,
                                        stroke_color_rgba = self.color_c,
                                        line_width = 1.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        ))
        

    def redraw(self, trace=None, action=None, obj=None):
        for l in self.lines:
            l.remove()
        self.lines=[]
        for m in self.marks:
            m.remove()
        self.marks=[]
        for t in self.timemarks:
            t.remove()
        self.timemarks=[]
        self.drawtimemarks()
        if 'actions' not in trace.levels.keys():
            return
        for a in trace.levels['actions']:
            for o in a.operations:
                self.addLine(o.movietime)
        self.changeMarks(action, obj)

    def changeMarks(self, action=None, obj=None):
        for m in self.marks:
            m.remove()
        self.marks=[]
        if action is not None:
            color = ACTION_COLORS[ACTIONS.index(action.name)]
            #print "%s %s %s" % (action.name, ACTIONS.index(action.name), color)
            for op in action.operations:
                self.addMark(op.movietime, color)
        elif obj is not None:
            for op in obj.cobj['opes']:
                self.addMark(op.movietime, 0xD9D919FF)

    def addMark(self, time=0, color='gray'):
        offset = 3
        x=self.rect.get_bounds().x1 + self.w * time / self.movielength
        x1 = x-offset
        x2 = x+offset
        y2=self.rect.get_bounds().y1
        y1=y2-offset
        p = goocanvas.Points ([(x1, y1), (x, y2), (x2, y1)])
        l = goocanvas.Polyline (parent = self,
                                        close_path = False,
                                        points = p,
                                        stroke_color_rgba = color,
                                        line_width = 2.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        )
        self.marks.append(l)

    def changeMovielength(self, trace=None, time=None):
        if time is not None:
            self.movielength=time
        elif self.controller.package.cached_duration>0:
            self.movielength=self.controller.package.cached_duration
        self.redraw(trace)
        

    def addLine(self, time=0, color=0x00000050, offset=0):
        # to be removed
        #~ if self.controller.package.cached_duration > self.movielength:
            #~ self.movielength=self.controller.package.cached_duration
        # assuming there is no more movielength problem
        x=self.rect.get_bounds().x1 + self.w * time / self.movielength
        y1=self.rect.get_bounds().y1 - offset
        y2=self.rect.get_bounds().y2 + offset
        p = goocanvas.Points ([(x, y1), (x, y2)])
        #ld = goocanvas.LineDash([3.0, 3.0])
        l = goocanvas.Polyline (parent = self,
                                        close_path = False,
                                        points = p,
                                        stroke_color_rgba = color,
                                        line_width = 1.0,
                                        #line_dash=ld,
                                        start_arrow = False,
                                        end_arrow = False
                                        )
        self.lines.append(l)

    def docgroup_clicked(self, w, t, ev):
        if ev.button == 1:
            c=self.controller
            pos = c.create_position (value=self.movielength * (ev.x-self.x)/self.w,
                                     key=c.player.MediaTime,
                                     origin=c.player.AbsolutePosition)
            c.update_status (status="set", position=pos)


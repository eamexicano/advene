"""VLC library functions."""

import advene.core.config as config
import os
import sys
import time
import Image
import StringIO
import inspect

from gettext import gettext as _

from advene.model.annotation import Annotation, Relation
import advene.model.tal.context

def fourcc2rawcode (code):
    """VideoLan to PIL code conversion.
    
    Converts the FOURCC used by VideoLan into the corresponding
    rawcode specification used by the python Image module.

    @param code: the FOURCC code from VideoLan
    @type code: string
    @return: the corresponding PIL code
    @rtype: string
    """
    conv = { 'RV32' : 'BGRX' }
    fourcc = "%c%c%c%c" % (code & 0xff,
                           code >> 8 & 0xff,
                           code >> 16 & 0xff,
                           code >> 24)
    return conv[fourcc]

def snapshot2png (image, output=None):
    """Convert a VLC RGBPicture to PNG.
    
    output is either a filename or a stream. If not given, the image
    will be returned as a buffer.

    @param image: a VLC.RGBPicture
    @param output: the output stream or filename (optional)
    @type output: filename or stream
    @return: an image buffer (optional)
    @rtype: string
    """
    if image.height == 0:
        print "Error : %s" % a.data
        return ""
    i = Image.fromstring ("RGB", (image.width, image.height), image.data,
                          "raw", fourcc2rawcode(image.type))
    if output is not None:
        i.save (output, 'png')
        return ""
    else:
        ostream = StringIO.StringIO ()
        i.save(ostream, 'png')
        return ostream.getvalue()

def mediafile2id (mediafile):
    """Returns an id (with encoded /) corresponding to the mediafile.

    @param mediafile: the name of the mediafile
    @type mediafile: string
    @return: an id
    @rtype: string
    """
    return mediafile.replace ('/', '%2F')

def package2id (p):
    """Return the id of the package's mediafile.

    Return the id (with encoded /) corresponding to the mediafile
    defined in the package. Returns "undefined" if no mediafile is
    defined.

    @param p: the package
    @type p: advene.Package

    @return: the corresponding id
    @rtype: string
    """
    mediafile = p.getMetaData (config.data.namespace, "mediafile")
    if mediafile is not None and mediafile != "":
        return mediafile2id (mediafile)
    else:
        return "undefined"

def format_time (val=0):
    """Formats a value (in milliseconds) into a time string.

    @param val: the value
    @type val: int
    @return: the formatted string
    @rtype: string
    """ 
    t = long(val)
    # Format: HH:MM:SS.mmm
    return "%s.%03d" % (time.strftime("%H:%M:%S", time.gmtime(t / 1000)),
                       t % 1000)

def matching_relationtypes(package, ann1, ann2):
    """Return a list of relationtypes that can be used
    to link ann1 and ann2. We use the id (i.e. the fragment part from the URI)
    to match"""
    # FIXME: works only on binary relations for the moment.
    r=[]
    for rt in package.relationTypes:
        # Absolutize URIs
        # FIXME: horrible hack. Does not even work on
        # imported packages
        def absolute_uri(package, uri):
            if uri.startswith('#'):
                return package.uri + uri
            else:
                return uri

        def get_id(uri):
            try:
                i=uri[uri.index('#')+1:]
            except ValueError:
                i=uri
            return unicode(i)

        # URI version
        # lat=[ absolute_uri(package, t) for t in rt.getHackedMemberTypes() ]
        # t1=ann1.type.uri
        # t2=ann2.type.uri
        
        # Id version
        lat= [ get_id(t) for t in rt.getHackedMemberTypes() ]
        t1=get_id(ann1.type.uri)
        t2=get_id(ann2.type.uri)
        
        #print "Testing (%s, %s) matching %s" % (t1, t2, lat)
        if t1 == lat[0] and t2 == lat[1]:
            r.append(rt)
    #print "Matching: %s" % r
    return r

def get_title(controller, element):
    if isinstance(element, Annotation) or isinstance(element, Relation):
        expr=element.type.getMetaData(config.data.namespace, "display")
        if expr is None or expr == '':
            return element.content.data
        else:
            c=controller.event_handler.build_context(event='Display', here=element)
            return c.evaluateValue(expr)
    # FIXME: handle the other elements
    return str(element)

def get_valid_members (el):
    """Return a list of strings, valid members for the object el in TALES.

    This method is used to generate the contextual completion menu
    in the web interface and the browser view.

    @param el: the object to examine (often an Advene object)
    @type el: any

    @return: the list of elements which are members of the object,
             in the TALES meaning.
    @rtype: list
    """
    l = []
    try:
        l.extend(el.ids())
    except AttributeError:
        try:
            l.extend(el.keys())
        except AttributeError:
            pass

    c = type(el)
    l.extend([e[0]
              for e in inspect.getmembers(c)
              if isinstance(e[1], property) and e[1].fget is not None])

    # Global methods
    l.extend (advene.model.tal.context.AdveneContext.defaultMethods ())

    return l


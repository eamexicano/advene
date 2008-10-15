from bisect import insort
from itertools import chain
from weakref import ref

from advene.model.consts import _RAISE, PARSER_META_PREFIX
from advene.model.exceptions import ModelError
from advene.model.tales import tales_path1_function
from advene.utils.sorted_dict import SortedDict

class WithMetaMixin:
    """Metadata access mixin.

    I factorize all metadata-related code for classes Package and
    PackageElement.

    I also provide an alias mechanism to make frequent metadata easily
    accessible as python properties.

    FIXME: expand description with usage example
    """

    # NB: unlike other collections in the Advene model, metadata no not provide
    # means to get id-ref *only* for unreachable elements. Since metadata
    # already require a test (is the value a string value or an element value)
    # mixing "pure" strings, id-refs and elements would seem too cumbersome...

    __cache = None # SortedDict of all known metadata
                   # values are either string or (weakref, id)
    __cache_is_complete = False # is self.__cache complete?

    def iter_meta(self):
        """Iter over all the metadata of this object.

        Yields (key, value) pairs, where the value is either a string or an
        element. If the element is unreachable, value is None.

        See also `iter_meta_ids`.
        """
        if hasattr(self, "ADVENE_TYPE"):
            p = self._owner
            eid = self._id
            typ = self.ADVENE_TYPE
        else:
            p = self
            eid = ""
            typ = ""

        if self.__cache_is_complete:
            # then rely completely on cache
            for k, v in self.__cache.iteritems():
                if v is KeyError:
                    continue
                if isinstance(v, tuple):
                    tpl = v
                    v = tpl[0]()
                    if v is None:
                        v = p.get_element(tpl[1], None)
                yield k, v
        else:
            # retrieve data from backend and cache them
            cache = self.__cache
            complete = True
            if cache is None:
                cache = self.__cache = SortedDict()
            for k, v, v_is_id in p._backend.iter_meta(p._id, eid, typ):
                if v_is_id:
                    # it is no use looking in cache: if the element is in it,
                    # then it will also be in the package's cache, and the
                    # retrieval from the package will be as efficient
                    e = p.get_element(v, None)
                    if e is not None:
                        cache[k] = (ref(e), v)
                    else:
                        complete = False
                    v = e
                else:
                    cache[k] = v
                yield k, v
            self.__cache_is_complete = complete

    def iter_meta_ids(self):
        """Iter over all the metadata of this object.

        Yields (key, value) pairs, where the value is a string with a special
        attribute ``is_id`` indicating if it represents the id-ref of an
        element.

        See also `iter_meta`.
        """
        if hasattr(self, "ADVENE_TYPE"):
            p = self._owner
            eid = self._id
            typ = self.ADVENE_TYPE
        else:
            p = self
            eid = ""
            typ = ""

        if self.__cache_is_complete:
            # then rely completely on cache
            for k, v in self.__cache.iteritems():
                if v is KeyError:
                    continue
                if isinstance(v, tuple):
                    v = metadata_value(v[1], True)
                else:
                    v = metadata_value(v, False)
                yield k, v
        else:
            # retrieve data from backend
            cache = self.__cache
            for k, v, v_is_id in p._backend.iter_meta(p._id, eid, typ):
                yield k, metadata_value(v, v_is_id)

    def get_meta(self, key, default=_RAISE):
        """Return the metadata (string or element) associated to the given key.

        If no metadata is associated to the given key, a KeyError is raised.
        If the given key references an unreachable element, a 
        `NoSuchElementError` or `UnreachableImportError` is raised.

        All exceptions can be avoided by providing a ``default`` value, that
        will be returned instead of raising an exception.
        """
        return self.get_meta_id(key, default, False)

    def get_meta_id(self, key, default=_RAISE, _return_id=True):
        """Return the metadata id (string or element) associated to the given key.

        The returned value is a string with a special attribute ``is_id``
        indicating if it represents the id-ref of an element.

        If no metadata is associated to the given key, a KeyError is raised,
        unless ``default`` is provideded, in which case its value is returned
        instead.
        """
        # NB: this method actually implement both get_meta and get_meta_ids,
        # with the flag _return_id to choose between the two.

        if hasattr(self, "ADVENE_TYPE"):
            p = self._owner
            eid = self._id
            typ = self.ADVENE_TYPE
        else:
            p = self
            eid = ""
            typ = ""
        cache = self.__cache
        if cache is None:
            cache = self.__cache = SortedDict()

        val = cache.get((key))
        if isinstance(val, tuple):
            if _return_id:
                val = metadata_value(val[1], True)
            else:
                wref, the_id = val
                val = wref()
                if val is None:
                    val = p.get_element(the_id, default)
                    if val is not default:
                        cache[key] = (ref(val), the_id)
        elif isinstance(val, basestring):
            if _return_id:
                val = metadata_value(val, False)
        elif val is None: # could also be KeyError
            tpl = p._backend.get_meta(p._id, eid, typ, key)
            if tpl is None:
                val = cache[key] = KeyError
            else:
                if _return_id:
                    val = metadata_value(*tpl)
                elif tpl[1]:
                    the_id = tpl[0]
                    val = p.get_element(the_id, default)
                    if val is not default:
                        cache[key] = (ref(val), tpl[0])
                else:
                    val = cache[key] = tpl[0]

        if val is KeyError: # from cache or set above
            if default is _RAISE:
                raise KeyError(key)
            else:
                val = default
        return val

    def set_meta(self, key, val):
        """Set the metadata.

        ``val`` can either be a PackageElement or a string. If an element, it
        must be directly imported by the package of self, or a ModelError will
        be raised.
        """
        if hasattr(self, "ADVENE_TYPE"):
            p = self._owner
            eid = self._id
            typ = self.ADVENE_TYPE
        else:
            p = self
            eid = ""
            typ = ""
        if hasattr(val, "ADVENE_TYPE"):
            if not p._can_reference(val):
                raise ModelError, "Element should be directy imported"
            vstr = val.make_id_in(p)
            vstr_is_id = True
            val = (ref(val), vstr)
        else:
            vstr = str(val)
            vstr_is_id = False
        cache = self.__cache
        if cache is None:
            cache = self.__cache = SortedDict()
        cache[key] = val
        p._backend.set_meta(p._id, eid, typ, key, vstr, vstr_is_id)

    def del_meta(self, key):
        """Delete the metadata.

        Note that if the given key is not in use, this will have no effect.
        """
        if hasattr(self, "ADVENE_TYPE"):
            p = self._owner
            eid = self._id
            typ = self.ADVENE_TYPE
        else:
            p = self
            eid = ""
            typ = ""
        cache = self.__cache
        if cache is not None and key in cache:
            del cache[key]
        p._backend.set_meta(p._id, eid, typ, key, None, False)

    @property
    def meta(self):
        return _MetaDict(self)

    @classmethod
    def make_metadata_property(cls, key, alias=None):
        """Attempts to create a python property in cls mapping to metadata key.

        If alias is None, key is considered as a URI, and the last part of
        that URI (after # or /) is used.

        Raises an AttributeError if cls already has a member with that name.

        FIXME: should attach docstring to the property somehow
        """
        if alias is None:
            cut = max(key.rfind("#"), key.rfind("/"))
            alias = key[cut+1:]

        if hasattr(cls, alias):
            raise AttributeError(alias)

        def getter(obj):
            return obj.get_meta(key)

        def setter(obj, val):
            return obj.set_meta(key, val)

        def deller(obj):
            return self.del_meta(key)

        setattr(cls, alias, property(getter, setter, deller))

    @tales_path1_function
    def _tales_meta(self, path):
        nsd = self._get_ns_dict()
        return _PrefixDict(self, nsd[path])

    def _get_ns_dict(self):
        if hasattr(self, "ADVENE_TYPE"):
            package = self.ownet
        else:
            package = self
        namespaces = {}
        prefixes = package.get_meta(PARSER_META_PREFIX + "namespaces", "")
        for line in prefixes.split("\n"):
            if line:
                prefix, uri = line.split(" ")
                namespaces[prefix] = uri
        return namespaces
        
        

class _MetaDict(object):
    """A dict-like object representing the metadata of an object.

    Note that many methods have an equivalent with suffix ``_id`` or 
    ``_ids`` which use `get_meta_id` instead of `get_meta` and 
    `iter_meta_ids` instead of `iter_meta`, respectively.
    """ 

    __slots__ = ["_owner",]

    def __init__ (self, owner):
        self._owner = owner

    def __contains__(self, k):
        return self.get_meta(k, None) is not None

    def __delitem__(self, k):
        return self._owner.del_meta(k)

    def __getitem__(self, k):
        return self._owner.get_meta(k)

    def __iter__(self):
        return ( k for k, _ in self._owner.iter_meta_ids() )

    def __len__(self):
        return len(list(iter(self)))

    def __setitem__(self, k, v):
        return self._owner.set_meta(k, v)

    def clear(self):
        for k in self.keys():
            self._owner.del_meta(k)

    def copy(self):
        return dirt(self)

    def get(self, k, v=None):
        return self._owner.get_meta(k, v)

    def get_id(self, k, v=None):
        return self._owner.get_meta_id(k, v)

    def has_key(self, k):
        return self._owner.get_meta(k, None) is not None

    def items(self):
        return list(self._owner.iter_meta())

    def items_ids(self):
        return list(self._owner.iter_meta_ids())

    def iteritems(self):
        return self._owner.iter_meta()

    def iteritems_ids(self):
        return self._owner.iter_meta_ids()

    def iterkeys(self):
        return ( k for k, _ in self._owner.iter_meta_ids() )

    def itervalues(self):
        return ( v for _, v in self._owner.iter_meta() )

    def itervalues_ids(self):
        return ( v for _, v in self._owner.iter_meta_ids() )

    def keys(self):
        return [ k for k, _ in self._owner.iter_meta_ids() ]

    def pop(self, k, d=_RAISE):
        v = self._owner.get_meta(k, None)
        if v is None:
            if d is _RAISE:
                raise KeyError, k
            else:
                v = d
        else:
            self._owner.del_meta(k)
        return v

    def pop_id(self, k, d=_RAISE):
        v = self._owner.get_meta_id(k, None)
        if v is None:
            if d is _RAISE:
                raise KeyError, k
            else:
                v = d
        else:
            self._owner.del_meta(k)
        return v

    def popitem(self):
        it = self._owner.iter_meta()
        try:
            k, v = it.next()
        except StopIteration:
            raise KeyError()
        else:
            self._owner.del_meta(k)
            return v

    def popitem_id(self):
        it = self._owner.iter_meta_ids()
        try:
            k, v = it.next()
        except StopIteration:
            raise KeyError()
        else:
            self._owner.del_meta(k)
            return v

    def setdefault(self, k, d=""):
        assert isinstance(d, basestring) or hasattr(d, "ADVENE_TYPE")
        v = self._owner.get_meta(k, None)
        if v is None:
            self._owner.set_meta(k, d)
            v = d
        return v

    def update(self, e=None, **f):
        e_keys = getattr(e, "keys", None)
        if callable(e_keys):
            for k in e_keys():
                self._owner.set_meta(k, e[k])
        elif e is not None:
            for k, v in e:
                self._owner.set_meta(k, v)
        for k, v in f.iteritems():
            self._owner.set_meta(k, v)

    def values(self):
        return [ v for _, v in self._owner.iter_meta() ]

    def values_ids(self):
        return [ v for _, v in self._owner.iter_meta_ids() ]


class _PrefixDict(object):
    """
    A dict-like object used as an intermediate object in TALES expression.
    """
    __slots__ = ["_obj", "_prefix"]

    def __init__(self, obj, prefix):
        self._obj = obj
        self._prefix = prefix

    def __getitem__(self, path):
        return self._obj.get_meta(self._prefix+path)

    def __call__(self):
        # TODO use iter_meta(prefix=X) when implemented
        return ( (k[len(self._prefix):], v)
                 for k,v in self._obj.iter_meta()
                 if k.startswith(self._prefix))

class metadata_value(str):
    def __new__ (cls, val, is_id):
        return str.__new__(cls, val)
    def __init__ (self, val, is_id):
        self.is_id = is_id

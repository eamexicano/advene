#
# Advene: Annotate Digital Videos, Exchange on the NEt
# Copyright (C) 2008-2012 Olivier Aubert <olivier.aubert@liris.cnrs.fr>
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
"""
Merge packages
==============
"""

import sys
import os
import filecmp
import shutil

import advene.core.config as config

from advene.model.package import Package
from advene.model.annotation import Annotation, Relation
from advene.model.schema import Schema, AnnotationType, RelationType
from advene.model.view import View
from advene.model.query import Query
import advene.util.helper as helper

class Differ:
    """Returns a structure diff of two packages.
    """
    def __init__(self, source=None, destination=None, controller=None):
        self.source=source
        self.destination=destination
        self.controller=controller
        # translated ids for different elements with the same id.  The
        # key is the id in the source package, the value the (new) id
        # in the destination package.
        self.translated_ids = {}

    def diff(self):
        """Iterator returning a changelist.

        Structure of returned elements:
        (action_name, source_element, dest_element, action)
        """
        for m in (self.diff_schemas,
                  self.diff_annotation_types,
                  self.diff_relation_types,
                  self.diff_annotations,
                  self.diff_relations,
                  self.diff_views,
                  self.diff_queries,
                  self.diff_resources):
            for d in m():
                yield d

    def check_meta(self, s, d, namespaceid, name):
        ns=config.data.namespace_prefix[namespaceid]
        if s.getMetaData(ns, name) != d.getMetaData(ns, name):
            return ('update_meta_%s' % name,
                    s, d,
                    lambda s, d: self.update_meta(s, d, namespaceid, name) )
        else:
            return None

    def update_meta(self, s, d, namespaceid, name):
        """Update the meta attribute name from the given namespace.
        """
        ns=config.data.namespace_prefix[namespaceid]
        d.setMetaData(ns, name,
                      s.getMetaData(ns, name))


    def diff_schemas(self):
        for s in self.source.schemas:
            d=self.destination.get_element_by_id(s.id)
            if d is None:
                yield ('new', s, None, lambda s, d: self.copy_schema(s) )
            elif isinstance(d, type(s)):
                # Present. Check if it was modified
                if s.title != d.title:
                    yield ('update_title', s, d, lambda s, d: d.setTitle(s.title) )
                c=self.check_meta(s, d, 'dc', 'description')
                if c:
                    yield c
            else:
                # Same id, but different type. Generate a new type
                yield ('new', s, None, lambda s, d: self.copy_schema(s, True) )

    def diff_annotation_types(self):
        for s in self.source.annotationTypes:
            d=self.destination.get_element_by_id(s.id)
            if d is None:
                yield ('new', s, None, lambda s, d: self.copy_annotation_type(s) )
            elif isinstance(d, type(s)):
                # Present. Check if it was modified
                if s.title != d.title:
                    yield ('update_title', s, d, lambda s, d: d.setTitle(s.title) )
                if s.mimetype != d.mimetype:
                    yield ('update_mimetype', s, d, lambda s, d: d.setMimetype(s.mimetype) )
                c=self.check_meta(s, d, 'dc', 'description')
                if c:
                    yield c
                c=self.check_meta(s, d, 'advenetool', 'representation')
                if c:
                    yield c
                c=self.check_meta(s, d, 'advenetool', 'color')
                if c:
                    yield c
                c=self.check_meta(s, d, 'advenetool', 'item_color')
                if c:
                    yield c
            else:
                yield ('new', s, None, lambda s, d: self.copy_annotation_type(s, True) )

    def diff_relation_types(self):
        for s in self.source.relationTypes:
            d=self.destination.get_element_by_id(s.id)
            if d is None:
                yield ('new', s, None, lambda s, d: self.copy_relation_type(s) )
            elif isinstance(d, type(s)):
                # Present. Check if it was modified
                if s.title != d.title:
                    yield ('update_title', s, d, lambda s, d: d.setTitle(s.title) )
                if s.mimetype != d.mimetype:
                    yield ('update_mimetype', s, d, lambda s, d: d.setMimetype(s.mimetype) )
                c=self.check_meta(s, d, 'dc', 'description')
                if c:
                    yield c
                c=self.check_meta(s, d, 'advenetool', 'color')
                if c:
                    yield c
                c=self.check_meta(s, d, 'advenetool', 'item_color')
                if c:
                    yield c
                if s.hackedMemberTypes != d.hackedMemberTypes:
                    yield ('update_member_types', s, d, lambda s, d: d.setHackedMemberTypes( s.hackedMemberTypes ))
            else:
                yield ('new', s, None, lambda s, d: self.copy_relation_type(s, True) )


    def diff_annotations(self):
        for s in self.source.annotations:
            d=self.destination.get_element_by_id(s.id)
            if d is None:
                yield ('new', s, None, lambda s, d: self.copy_annotation(s) )
            elif isinstance(d, type(s)):
                # check type and author/date. If different, it is very
                # likely that it is in fact a new annotation, with
                # duplicate id.
                if s.type.id != d.type.id:
                    yield ('new_annotation', s, d, lambda s, d: self.copy_annotation(s, True))
                    continue
                if s.author != d.author and s.date != d.date:
                    # New annotation.
                    yield ('new_annotation', s, d, lambda s, d: self.copy_annotation(s, True))
                    continue
                # Present. Check if it was modified
                if s.fragment.begin != d.fragment.begin:
                    yield ('update_begin', s, d, lambda s, d: d.fragment.setBegin(s.fragment.begin))
                if s.fragment.end != d.fragment.end:
                    yield ('update_end', s, d, lambda s, d: d.fragment.setEnd(s.fragment.end))
                if s.content.data != d.content.data:
                    yield ('update_content', s, d, lambda s, d: d.content.setData(s.content.data))
                if s.tags != d.tags:
                    yield ('update_tags', s, d, lambda s, d: d.setTags( s.tags ))
            else:
                yield ('new', s, None, lambda s, d: self.copy_annotation(s, True) )


    def diff_relations(self):
        for s in self.source.relations:
            d=self.destination.get_element_by_id(s.id)
            if d is None:
                yield ('new', s, None, lambda s, d: self.copy_relation(s) )
            elif isinstance(d, type(s)):
                # check author/date. If different, it is very
                # likely that it is in fact a new relation, with
                # duplicate id.
                if s.type.id != d.type.id:
                    yield ('new_relation', s, d, lambda s, d: self.copy_relation(s, True))
                    continue
                if s.author != d.author and s.date != d.date:
                    # New relation.
                    yield ('new_relation', s, d, lambda s, d: self.copy_relation(s, True))
                    continue
                # Present. Check if it was modified
                if s.content.data != d.content.data:
                    yield ('update_content', s, d, lambda s, d: d.content.setData(s.content.data))
                sm=[ a.id for a in s.members ]
                dm=[ a.id for a in d.members ]
                if sm != dm:
                    yield ('update_members', s, d, self.update_members)
                if s.tags != d.tags:
                    yield ('update_tags', s, d, lambda s, d: d.setTags( s.tags ))
            else:
                yield ('new', s, None, lambda s, d: self.copy_relation(s, True) )

    def diff_views(self):
        for s in self.source.views:
            d=self.destination.get_element_by_id(s.id)
            if d is None:
                yield ('new', s, None, lambda s, d: self.copy_view(s) )
            elif isinstance(d, type(s)):
                # Present. Check if it was modified
                if s.title != d.title:
                    yield ('update_title', s, d, lambda s, d: d.setTitle(s.title) )
                if (s.matchFilter['class'] != d.matchFilter['class']
                    or s.matchFilter.get('type', None) != d.matchFilter.get('type', None)):
                    yield ('update_matchfilter', s, d, lambda s, d: d.matchFilter.update(s.matchFilter) )
                if s.content.mimetype != d.content.mimetype:
                    yield ('update_mimetype', s, d, lambda s, d: d.content.setMimetype(s.content.mimetype) )
                if s.content.data != d.content.data:
                    yield ('update_content', s, d, lambda s, d: d.content.setData(s.content.data))
            else:
                yield ('new', s, None, lambda s, d: self.copy_view(s, True) )

    def diff_queries(self):
        for s in self.source.queries:
            d=self.destination.get_element_by_id(s.id)
            if d is None:
                yield ('new', s, None, lambda s, d: self.copy_query(s) )
            elif isinstance(d, type(s)):
                # Present. Check if it was modified
                if s.title != d.title:
                    yield ('update_title', s, d, lambda s, d: d.setTitle(s.title) )
                if s.content.mimetype != d.content.mimetype:
                    yield ('update_mimetype', s, d, lambda s, d: d.setMimetype(s.mimetype) )
                if s.content.data != d.content.data:
                    yield ('update_content', s, d, lambda s, d: d.content.setData(s.content.data))
            else:
                yield ('new', s, None, lambda s, d: self.copy_query(s, True) )

    def diff_resources(self):
        if self.source.resources is None or self.destination.resources is None:
            # FIXME: warning message ?
            return
        sdir=self.source.resources.dir_
        ddir=self.destination.resources.dir_

        d=filecmp.dircmp(sdir, ddir)

        def relative_path(origin, dirname, name):
            """Return the relative path (hence id) for the resource 'name' in resource dir 'dirname',
            relative to the origin dir.
            """
            return os.path.join(dirname, name).replace(origin, '')

        def handle_dircmp(dc):
            for n in dc.left_only:
                yield ('create_resource',
                       relative_path(sdir, dc.left, n),
                       relative_path(ddir, dc.right, n), self.create_resource)
            for n in dc.diff_files:
                yield ('update_resource',
                       relative_path(sdir, dc.left, n),
                       relative_path(ddir, dc.right, n), self.update_resource)

        for t in handle_dircmp(d):
            yield t

        for sd in d.subdirs.itervalues():
            for t in handle_dircmp(sd):
                yield t
        return

    def copy_schema(self, s, generate_id=False):
        if generate_id or self.destination.get_element_by_id(s.id):
            id_=self.destination._idgenerator.get_id(Schema)
        else:
            id_ = s.id
        self.destination._idgenerator.add(id_)
        self.translated_ids[s.id]=id_

        el=self.destination.createSchema(ident=id_)
        el.author=s.author or self.source.author
        el.date=s.date or self.controller.get_timestamp()
        el.title=s.title or id_
        self.destination.schemas.append(el)
        return el

    def copy_annotation_type(self, s, generate_id=False):
        if generate_id or self.destination.get_element_by_id(s.id):
            id_=self.destination._idgenerator.get_id(AnnotationType)
        else:
            id_ = s.id
        self.destination._idgenerator.add(id_)
        self.translated_ids[s.id]=id_

        # Find parent, and create it if necessary
        sch=helper.get_id(self.destination.schemas, s.schema.id)
        if not sch:
            # Create it
            sch=helper.get_id(self.source.schemas, s.schema.id)
            sch=self.copy_schema(sch)
        el=sch.createAnnotationType(ident=id_)
        el.author=s.author or self.source.author
        el.date=s.date or self.controller.get_timestamp()
        el.title=s.title or id_
        el.mimetype=s.mimetype
        for n in ('color', 'item_color'):
            el.setMetaData(config.data.namespace, n, (s.getMetaData(config.data.namespace, n) or ''))
        sch.annotationTypes.append(el)
        return el

    def copy_relation_type(self, s, generate_id=False):
        if generate_id or self.destination.get_element_by_id(s.id):
            id_=self.destination._idgenerator.get_id(RelationType)
        else:
            id_ = s.id
        self.destination._idgenerator.add(id_)
        self.translated_ids[s.id]=id_

        # Find parent, and create it if necessary
        sch=helper.get_id(self.destination.schemas, s.schema.id)
        if not sch:
            # Create it
            sch=helper.get_id(self.source.schemas, s.schema.id)
            sch=self.copy_schema(sch)
        el=sch.createRelationType(ident=id_)
        el.author=s.author or self.source.author
        el.date=s.date or self.controller.get_timestamp()
        el.title=s.title or id_
        el.mimetype=s.mimetype
        sch.relationTypes.append(el)
        el.setMetaData(config.data.namespace, 'color', s.getMetaData(config.data.namespace, 'color'))
        # Handle membertypes, ensure that annotation types are defined
        for m in s.hackedMemberTypes:
            if m == '':
                # Any type, no import necessary
                continue
            if not m.startswith('#'):
                print "Cannot handle non-fragment membertypes", m
                continue
            at=helper.get_id(self.destination.annotationTypes, m[1:])
            if not at:
                # The annotation type does not exist. Create it.
                at=helper.get_id(self.source.annotationTypes, m[1:])
                at=self.copy_annotation_type(at)
        # Now we can set member types
        el.setHackedMemberTypes(s.getHackedMemberTypes())
        return el

    def update_members(self, s, d):
        """Update the relation members.
        """
        sm=[ a.id for a in s.members ]
        d.members.clear()
        for i in sm:
            # Handle translated ids
            if i in self.translated_ids:
                i=self.translated_ids[i]
            a=helper.get_id(self.destination.annotations, i)
            if a is None:
                raise "Error: missing annotation %s" % i
            d.members.append(a)
        return d

    def copy_annotation(self, s, generate_id=False):
        """Create a new annotation.

        If generate_id is True, then generate a new id. Else, use the
        source id.

        Try to keep track of the occurences of its id, to fix them later on.
        """
        if generate_id or self.destination.get_element_by_id(s.id):
            id_ = self.destination._idgenerator.get_id(Annotation)
        else:
            id_ = s.id
        self.destination._idgenerator.add(id_)
        self.translated_ids[s.id]=id_

        # Find parent, and create it if necessary
        at=helper.get_id(self.destination.annotationTypes, s.type.id)
        if not at:
            # The annotation type does not exist. Create it.
            at=self.copy_annotation_type(helper.get_id(self.source.annotationTypes,
                                                       s.type.id))
        el=self.destination.createAnnotation(
            ident=id_,
            type=at,
            author=s.author or self.source.author,
            fragment=s.fragment.clone())
        el.date=s.date or self.controller.get_timestamp()
        el.content.data=s.content.data
        self.destination.annotations.append(el)
        return el

    def copy_relation(self, s, generate_id=False):
        if generate_id or self.destination.get_element_by_id(s.id):
            id_=self.destination._idgenerator.get_id(Relation)
        else:
            id_ = s.id
        self.destination._idgenerator.add(id_)
        self.translated_ids[s.id]=id_

        rt=helper.get_id(self.destination.relationTypes, s.type.id)
        if not rt:
            # The annotation type does not exist. Create it.
            rt=self.copy_relation_type(helper.get_id(self.source.relationTypes,
                                                     s.type.id))
        # Ensure that annotations exist
        members=[]
        for sa in s.members:
            # check translated_ids
            i=sa.id
            if i in self.translated_ids:
                i=self.translated_ids[i]

            a=helper.get_id(self.destination.annotations, i)
            if not a:
                a=self.copy_annotation(sa)
            members.append(a)
        el=self.destination.createRelation(
            ident=id_,
            type=rt,
            author=s.author or self.source.author,
            members=members)
        el.date=s.date or self.controller.get_timestamp()
        el.content.data=s.content.data
        self.destination.relations.append(el)
        #el.title=s.title or ''
        return el

    def copy_query(self, s, generate_id=False):
        if generate_id or self.destination.get_element_by_id(s.id):
            id_=self.destination._idgenerator.get_id(Query)
        else:
            id_ = s.id
        self.destination._idgenerator.add(id_)
        self.translated_ids[s.id]=id_

        el=self.destination.createQuery(
            ident=id_,
            author=s.author or self.source.author)
        el.data=s.date or self.controller.get_timestamp()
        el.title=s.title or id_
        el.content.data=s.content.data
        el.content.mimetype=s.content.mimetype
        self.destination.queries.append(el)
        return el

    def copy_view(self, s, generate_id=False):
        if generate_id or self.destination.get_element_by_id(s.id):
            id_=self.destination._idgenerator.get_id(View)
        else:
            id_ = s.id
        self.destination._idgenerator.add(id_)
        self.translated_ids[s.id]=id_

        el=self.destination.createView(
            ident=id_,
            clazz=s.viewableClass,
            author=s.author or self.source.author)
        el.date=s.date or self.controller.get_timestamp()
        el.title=s.title or id_
        el.matchFilter['class']=s.matchFilter['class']
        if s.matchFilter.has_key('type'):
            el.matchFilter['type']=s.matchFilter['type']
        # FIXME: ideally, we should try to fix translated_ids in
        # views. Or at least try to signal possible occurrences.
        el.content.data=s.content.data
        el.content.mimetype=s.content.mimetype
        self.destination.views.append(el)
        return el

    def create_resource(self, s, d):
        source_name=os.path.join(self.source.resources.dir_, d)
        destination_name=os.path.join(self.destination.resources.dir_, d)
        if not os.path.exists(source_name):
            print "Package integrity problem: %s does not exist" % source_name
            return
        if os.path.isdir(source_name):
            shutil.copytree(source_name, destination_name)
        else:
            shutil.copyfile(source_name, destination_name)

    def update_resource(self, s, d):
        source_name=os.path.join(self.source.resources.dir_, d)
        destination_name=os.path.join(self.destination.resources.dir_, d)
        for rep in (source_name, destination_name):
            if not os.path.exists(rep):
                print "Package integrity problem: %s does not exist" % source_name
                return
        shutil.copyfile(source_name, destination_name)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print "Should provide 2 package names"
        sys.exit(1)

    sourcename=sys.argv[1]
    destname=sys.argv[2]

    print sourcename, destname
    source=Package(uri=sourcename)
    dest=Package(uri=destname)

    differ=Differ(source, dest)
    diff=differ.diff()
    for name, s, d, action in diff:
        print name, unicode(s).encode('utf-8'), unicode(d).encode('utf-8')
        #action(s, d)
    #dest.save('foo.xml')

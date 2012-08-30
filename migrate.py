#!/usr/bin/python
# -*- coding: utf-8 -*-
import ConfigParser
import sys
import os
import logging
from xml.etree.ElementTree import dump
import pickle

# third-party modules
import yaml
from smugpy import SmugMug
import flickrapi

#logging.basicConfig()

log = logging.getLogger('migrate')
log.setLevel(logging.INFO)

config = ConfigParser.ConfigParser()
try:
    config.readfp(open('secrets.cfg'))
except e:
    print(e.msg)

def save():
    with open('secrets.cfg', 'wb') as configfile:
        config.write(configfile)

# Smooth over python 2->3 differences
if sys.version_info < (3,):
    get_input = raw_input
else:
    get_input = input

class flickr_token_cache(object):
    """
    Simple little config-file backed token cache for flickrapi
    """
    def __init__(self, c):
        self.config = c

    def get_token(self):
        if self.config.has_option('flickr', 'oauth_token'):
            return self.config.get('flickr', 'oauth_token')
        return None

    def set_cached_token(self, token):
        self.config.set('flickr', 'oauth_token', token)
        save()

    def forget(self):
        try:
            self.config.remove_option('flickr', 'oauth_token')
            save()
        except NoSectionError:
            return

    token = property(get_token, set_cached_token, forget, "The cached token")

class flickr:
    def __init__(self):
        self.client = None

    def auth(self):
        flickr = flickrapi.FlickrAPI(config.get('flickr', 'key'), config.get('flickr', 'secret'))
        flickr.token_cache = flickr_token_cache(config)
        (token,frob) = flickr.get_token_part_one(perms='read')
        if not token:
            raw_input('Authorize app and press ENTER when complete')
        flickr.get_token_part_two((token,frob))
        self.client= flickr

    def check_pro(self):
        try:
            res = self.client.people_findByUsername(username=config.get('flickr', 'username'))[0]
            nsid = res.attrib['nsid']
            res = self.client.people_getInfo(user_id=nsid)[0]
            return res.attrib['ispro'] == '1'
        except flickrapi.FlickrError, e:
            return False

    def list_sets(self):
        sets = self.client.photosets_getList()
        return sets.find('photosets').findall('photoset')

    def dump_sets(self, output_dir, overwrite=False):
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        for set in self.list_sets():
            title = set.find('title').text
            desc = set.find('description').text
            set_metadata = {  'title': set.find('title').text,
                              'description': set.find('description').text,
                              'id': set.attrib['id'],
                              'photos_count': set.attrib['photos'],
                              'videos_count': set.attrib['videos'],
                              'primary': set.attrib['primary'],
                              'contents': [] }
            meta_f = '%s/%s.pkl' % (output_dir, set_metadata['id'])
            if os.path.exists(meta_f) and not overwrite:
                log.info("flickr: skipping set '%s'" % (set_metadata['title']))
                continue
            log.info("flickr: saving set '%s'" % (set_metadata['title']))
            for photo in self.client.walk_set(set.attrib['id']):
                id = photo.attrib['id']
                photo = self.client.photos_getInfo(photo_id=id)[0]
                secret = photo.attrib['originalsecret']
                format = photo.attrib['originalformat']
                farm = photo.attrib['farm']
                server = photo.attrib['server']
                source_url = "http://farm%s.staticflickr.com/%s/%s_%s_o.%s" %( farm, server, id, secret, format )

                try:
                    tags = []
                    for tag in photo.find('tags').findall('tag'):
                        tags.append( tag.attrib['raw'] )
                except AttributeError,e:
                    log.debug("flickr: photo %s no tags found" (id))

                photo_metadata = {  'title': photo.find('title').text,
                                    'id': photo.attrib['id'],
                                    'description': photo.find('description').text,
                                    'tags': tags,
                                    'url': source_url }
                set_metadata['contents'].append(photo_metadata)
            with open(meta_f, 'wb') as set_file:
                pickle.dump(set_metadata, set_file)

class smugmug:
    def __init__(self):
        self.client = None

    def auth(self):
        smugmug = SmugMug(api_key=config.get('smugmug', 'key'), oauth_secret=config.get('smugmug', 'secret'), api_version="1.3.0", app_name="flickr-to-smugmug")
        if config.has_option('smugmug', 'oauth_token'):
            smugmug.set_oauth_token(config.get('smugmug', 'oauth_token'), config.get('smugmug', 'oauth_token_secret'))
        else:
            smugmug.auth_getRequestToken()
            get_input("Authorize app at %s\n\nPress Enter when complete.\n" % (smugmug.authorize(access='Full', perm='Modify')))
            smugmug.auth_getAccessToken()
            config.set('smugmug', 'oauth_token', smugmug.oauth_token)
            config.set('smugmug', 'oauth_token_secret', smugmug.oauth_token_secret)
            save()
        self.client = smugmug

    def list_albums(self):
        albums = self.client.albums_get(NickName=config.get('smugmug', 'username'), Extras='Description')
        return albums['Albums']

    def album_find(self, title):
        albums = self.list_albums()
        for a in albums:
            if a['Title'] == title:
                return a
        return None

    def album_get(self, id):
        albums = self.list_albums()
        for a in albums:
            if a['id'] == id:
                return a
        return None

    def album_create(self, title, desc):
        resp = self.client.albums_create(Title=unicode(title).encode('utf-8'), Description=unicode(desc).encode('utf-8'), Public=False, Extras='Description')
        log.debug("smugmug: album_create %s" %(resp))
        if resp['stat'] == 'ok':
            log.info('smugmug: created album %s' %(title))
        else:
            log.error('smugmug: FAILED create album album %s' %(title))

        return resp['Album']

    def import_albums(self, input_dir, force=False):
        if not os.path.exists(input_dir):
            log.error("smugmug: can't import from %s" %(input_dir))
            return False

        sets = filter(lambda f: f.endswith('pkl'), os.listdir(input_dir))
        log.info("smugmug: %s sets ready for import" %(len(sets)))
        current = 0
        for f in sets:
            metadata = pickle.load(open("%s%s%s" % (input_dir,os.sep,f), 'rb'))
            current += 1
            log.info("smugmug: Processing set %s/%s: %s" % (current, len(sets), metadata['title']))
            log.debug("smugmug: file %s" % (f))

            if not metadata.get('smug_id', None) is None:
                album = self.album_get(metadata['smug_id'])
                log.info('smugmug: using cached album %s id:' %(metadata['title'], metadata['smug_id']))
            else:
                album = self.album_find(metadata['title'])
                log.info('smugmug: using existing album %s' %(metadata['title']))
            if album is None:
                album = self.album_create(metadata['title'], metadata['description'])
                metadata['smug_id'] = album['id']
            if album['Description'] != metadata['description']:
                resp = self.client.albums_changeSettings(AlbumID=album['id'], Description=metadata['description'])
                if resp['stat'] == 'ok':
                    log.info('smugmug: changed description for album %s' %(metadata['title']))
                else:
                    log.error('smugmug: FAILED change description for album %s' %(metadata['title']))

            current_photo = 0
            for index,photo in enumerate(metadata['contents']):
                current_photo += 1

                try:
                    if photo['smugmugged'] and not forced:
                        log.info('smugmug: Skipping photo %s/%s' %( current_photo, len(metadata['contents'])))
                        continue
                except KeyError:
                    pass

                log.info('smugmug: Uploading photo %s/%s' %( current_photo, len(metadata['contents'])))

                if len(photo['tags']) > 0:
                    tags = ",".join(photo['tags'])
                else:
                    tags = ''
                desc = photo['description']
                if desc is None or desc == "None":
                    desc = ''
                caption = "%s\n%s" %(photo['title'], desc)
                log.debug("smugmug: payload caption '%s'" %(caption))
                log.debug("smugmug: payload tags '%s'" %(tags))
                log.debug("smugmug: payload url '%s'" %(photo['url']))
                resp = self.client.images_uploadFromURL(AlbumID=album['id'], URL=photo['url'],
                                                        Caption=unicode(caption).encode('utf-8'),
                                                        Keywords=unicode(tags).encode('utf-8'))
                log.debug("smugmug: uploaded %s" %(resp))

                photo['smugmugged'] = resp['stat'] == 'ok'
                metadata['contents'][index] = photo

                # persist progress
                with open("%s%s%s" % (input_dir,os.sep,f), 'wb') as set_file:
                    pickle.dump(metadata, set_file)


log.info("Authenticating flickr")
f = flickr()
f.auth()

if not f.check_pro():
    print("User %s isn't a pro user, so original photos cannot be used")
    sys.exit(1)

log.info("Authenticating smugmug")
s = smugmug()
s.auth()

log.info("Fetching flickr metadata")
f.dump_sets("./tmp")
log.info("Flickr fetch complete")
log.info("Importing photos to Smugmug")
forced = False # TODO: make argument
s.import_albums("tmp", forced)



Flickr -> Smugmug
=================

A simple utility for migrating from Flickr to Smugmug. It is fast and
efficient by uploading photos directly from Flickr to Smugmug without
downloading them to your computer first.

This utility (currently command-line only) migrates the following data:

* Flickr Photosets -> Smugmug Albums\*
* Flickr Title and Description -> Smugmug Caption
* Flickr Tags -> Smugmug Keywords

Notably the following **are NOT** migrated:

* Flickr permissions
* Flickr collections
* Everything else not listed above

\* no de-duplication is performed if images exist in multiple Flickr photosetso

Licensed under the GPL v3 (see LICENSE)

## Requirements

* Smugmug account w/ API key
* Flickr account w/ API key (**PRO account is necessary** to fetch *original* images)

**Python Modules:**

You can install the necessary python modules with:

    pip install -U -r requirements.txt

Or, fetch the dependencies from their respective sites.

* [smugpy](https://github.com/chrishoffman/smugpy) - Smugmug Python library
* [flickrapi](http://stuvel.eu/flickrapi) - Flickr Python library

## Usage

1. Copy `secrets.cfg.example` to `secrets.cfg` and fill in the necessary
   information. *Everything* field is required.
2. Run the script `python migrate.py`

Temporary metadata will be saved to the current directory, so ensure it is
writeable.

If an error occurs, you can run the script again and it will attempt to resume
from where it left off.

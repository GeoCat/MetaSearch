MetaSearch Catalogue Client QGIS Plugin
=======================================

MetaSearch is a QGIS plugin to interact with CSW services.

```
$ git clone https://github.com/geopython/MetaSearch.git
$ cd MetaSearch
# install plugin dependencies
$ pip install -r requirements.txt --target=plugin/MetaSearch/ext-libs
# install developer requirements
$ pip install -r requirements-dev.txt
# link plugin to qgis2 runtime
$ ln -s path/to/MetaSearch/plugin $HOME/.qgis2/python/plugins

# or copy the entire plugin to $HOME/.qgis2/python/plugins
$ paver install
```

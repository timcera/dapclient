Templating
----------

dapclient uses an `experimental backend-agnostic templating API
<http://svn.pythonpaste.org/Paste/TemplateProposal/>`_ for rendering HTML and
XML by responses. Since the API is neutral dapclient can use any templating
engine, like `Mako <http://www.makotemplates.org/>`_ or `Genshi
<http://genshi.edgewall.org/>`_, and templates can be loaded from disk, memory
or a database. The server that comes with dapclient, for example, defines
a ``renderer`` object that loads Genshi templates from a directory
``templatedir``::

    from dapclient.util.template import FileLoader, GenshiRenderer

    class FileServer(object):
        def __init__(self, templatedir, ...):
            loader = FileLoader(templatedir)
            self.renderer = GenshiRenderer(options={}, loader=loader)
            ...

        def __call__(self, environ, start_response):
            environ.setdefault('dapclient.renderer', self.renderer)
            ...

And here is how the HTML response uses the renderer: the response requests
a template called ``html.html``, that is loaded from the directory by the
``FileLoader`` object, and renders it by passing the context::

    def serialize(dataset):
        ...
        renderer = environ['dapclient.renderer']
        template = renderer.loader('html.html')
        output = renderer.render(template, context, output_format='text/html')
        return [output]

(This is actually a simplification; if you look at the code you'll notice that
there's also code to fallback to a default renderer if one is not found in the
``environ``.)

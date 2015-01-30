"""Leverage curl to make XMLRPC requests that check the server's credentials."""

import xmlrpclib

import curlwrapper


class CertificateCheckingSafeTransport (xmlrpclib.Transport):

    def __init__(self, cacert, timeout):
        self.cacert = cacert
        self.timeout = timeout

    def request(self, host, handler, request_body, verbose=0):
        self.verbose = verbose
        url='https://%s%s' % (host, handler)
        # this might raise an xmlrpclib.Protocolerror exception
        contents = curlwrapper.retrieve(url,
                                        cacert = self.cacert,
                                        postdata = request_body,
                                        timeout = self.timeout)
        return xmlrpclib.loads(contents)[0]

class ServerProxy(xmlrpclib.ServerProxy):

    def __init__(self, uri, cacert, timeout = 300, **kwds):
        xmlrpclib.ServerProxy.__init__(self, uri,
                                       CertificateCheckingSafeTransport(cacert, timeout),
                                       **kwds)

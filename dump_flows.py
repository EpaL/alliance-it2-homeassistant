"""mitmproxy read-addon: dump each flow as URL + request/response bodies to stdout."""
from mitmproxy import http

def response(flow: http.HTTPFlow):
    try:
        req = flow.request
        print("\n===== %s %s =====" % (req.method, req.pretty_url), flush=True)
        if req.content:
            try:
                print("--- request body ---\n" + req.get_text(strict=False)[:4000], flush=True)
            except Exception:
                pass
        resp = flow.response
        if resp is not None and resp.content:
            try:
                print("--- response body ---\n" + resp.get_text(strict=False)[:8000], flush=True)
            except Exception:
                pass
    except Exception as e:
        print("(dump error: %s)" % e, flush=True)

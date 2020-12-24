from starlette.responses import RedirectResponse
from ..base_client import OAuthError
from ..base_client import BaseApp
from ..base_client.async_app import AsyncOAuth1Mixin, AsyncOAuth2Mixin
from ..base_client.async_openid import AsyncOpenIDMixin
from ..httpx_client import AsyncOAuth1Client, AsyncOAuth2Client


class StarletteAppMixin(object):
    async def save_authorize_data(self, request, **kwargs):
        state = kwargs.pop('state', None)
        if state:
            await self.framework.set_state_data(request.session, state, kwargs)
        else:
            raise RuntimeError('Missing state value')

    async def authorize_redirect(self, request, redirect_uri=None, **kwargs):
        """Create a HTTP Redirect for Authorization Endpoint.

        :param request: HTTP request instance from Django view.
        :param redirect_uri: Callback or redirect URI for authorization.
        :param kwargs: Extra parameters to include.
        :return: A HTTP redirect response.
        """
        rv = await self.create_authorization_url(redirect_uri, **kwargs)
        await self.save_authorize_data(request, redirect_uri=redirect_uri, **rv)
        return RedirectResponse(rv['url'], status_code=302)


class StarletteOAuth1App(StarletteAppMixin, AsyncOAuth1Mixin, BaseApp):
    client_cls = AsyncOAuth1Client

    async def authorize_access_token(self, request, **kwargs):
        params = dict(request.query_params)
        state = params.get('oauth_token')
        if not state:
            raise OAuthError(description='Missing "oauth_token" parameter')

        data = await self.framework.get_state_data(request.session, state)
        if not data:
            raise OAuthError(description='Missing "request_token" in temporary data')

        params['request_token'] = data['request_token']
        redirect_uri = data.get('redirect_uri')
        if redirect_uri:
            params['redirect_uri'] = redirect_uri

        params.update(kwargs)
        await self.framework.clear_state_data(request.session, state)
        return await self.fetch_access_token(**params)


class StarletteOAuth2App(StarletteAppMixin, AsyncOAuth2Mixin, AsyncOpenIDMixin, BaseApp):
    client_cls = AsyncOAuth2Client

    async def authorize_access_token(self, request, **kwargs):
        error = request.query_params.get('error')
        if error:
            description = request.query_params.get('error_description')
            raise OAuthError(error=error, description=description)

        params = {
            'code': request.query_params.get('code'),
            'state': request.query_params.get('state'),
        }

        state_data = await self.framework.get_state_data(request.session, params.get('state'))
        params = self._format_state_params(state_data, params)
        token = await self.fetch_access_token(**params, **kwargs)

        if 'id_token' in token and 'nonce' in params:
            userinfo = await self.parse_id_token(token, nonce=params['nonce'])
            token['userinfo'] = userinfo
        return token

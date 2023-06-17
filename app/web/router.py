from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import constr

import db
from config import settings

template_engine = Environment(loader=FileSystemLoader('web/templates'), enable_async=True, autoescape=True)

default_params = {
    'app_title': settings.web.app_title,
    'app_desc': settings.web.app_description,
    'web_url': settings.external_url,
    'acme_url': settings.external_url + '/acme/directory',
}


api = APIRouter(tags=['web'])


@api.get('/', response_class=HTMLResponse)
async def index():
    return await template_engine.get_template('index.html').render_async(**default_params)

if settings.web.enable_public_log:
    @api.get('/certificates', response_class=HTMLResponse)
    async def certificate_log():
        async with db.transaction(readonly=True) as sql:
            certs = [record async for record in sql("""
                select
                    serial_number, not_valid_before, not_valid_after, revoked_at,
                    (not_valid_after > now() and revoked_at is null) as is_valid,
                    (not_valid_after - not_valid_before) as lifetime,
                    (now() - not_valid_before) as age,
                    array((select domain from authorizations authz where authz.order_id = cert.order_id order by domain)) as domains
                from certificates cert
                group by serial_number
                order by not_valid_after desc
            """)]
        return await template_engine.get_template('cert-log.html').render_async(**default_params, certs=certs)

    @api.get('/certificates/{serial_number}', response_class=Response, responses={
        200: {'content': {'application/pem-certificate-chain': {}}}
    })
    async def download_certificate(serial_number: constr(regex='^[0-9A-F]+$')):
        async with db.transaction(readonly=True) as sql:
            pem_chain = await sql.value('select chain_pem from certificates where serial_number = $1', serial_number)
        if not pem_chain:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='unknown certificate')
        return Response(content=pem_chain, media_type='application/pem-certificate-chain')

    @api.get('/domains', response_class=HTMLResponse)
    async def domain_log():
        async with db.transaction(readonly=True) as sql:
            domains = [record async for record in sql("""
                select
                    authz.domain as domain_name,
                    min(cert.not_valid_before) as first_requested_at,
                    max(cert.not_valid_after) as expires_at,
                    max(cert.not_valid_after) FILTER (WHERE revoked_at is null) > now() AS is_valid
                from orders ord
                join authorizations authz on authz.order_id = ord.id
                join certificates cert on cert.order_id = ord.id
                group by authz.domain
                order by authz.domain
            """)]
        return await template_engine.get_template('domain-log.html').render_async(**default_params, domains=domains)
else:
    @api.get('/certificates')
    async def certificate_log():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='This page is disabled')

    @api.get('/domains')
    async def domain_log():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='This page is disabled')

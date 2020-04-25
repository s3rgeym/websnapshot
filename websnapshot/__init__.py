import asyncio
import logging
import pathlib
import re
import sys
from dataclasses import dataclass
from functools import partial
from typing import Any, Dict, List, TextIO
from urllib.parse import unquote

import click
from pyppeteer import launch

__version__ = '0.1.7'

# Символы запрещенные в именах файлов в Linux, Mac и Windows
UNSAFE_CHARACTERS = re.compile(r'[\\/:*?"<>|]+')

log = logging.getLogger(__name__)
click.option = partial(click.option, show_default=True)


def filename_from_url(url: str, extension: str) -> str:
    return UNSAFE_CHARACTERS.sub('_', unquote(url)) + extension


@dataclass
class ViewportSize:
    width: int
    height: int


async def worker(
    *,
    sem: asyncio.Semaphore,
    urls: asyncio.Queue,
    output_dirname: pathlib.Path,
    viewport_size: ViewportSize,
    headers: Dict[str, str],
    full_page: bool,
    quality: int,
    extension: str,
    delay: float,
    timeout: float
) -> None:
    log.info("worker started")
    browser = await launch()
    while not urls.empty():
        async with sem:
            try:
                url = await urls.get()
                page = await browser.newPage()
                await page.setViewport(
                    {
                        'width': viewport_size.width,
                        'height': viewport_size.height,
                    }
                )
                await page.setExtraHTTPHeaders(headers)
                # await page.setRequestInterception(True)

                # async def intercept(request):
                #     await request.continue_()

                # page.on(
                #     'request', lambda req: asyncio.ensure_future(intercept(req))
                # )
                await page.goto(url, {'timeout': int(timeout * 1000)})
                await asyncio.sleep(delay)
                filename = output_dirname.joinpath(
                    filename_from_url(url, extension)
                )
                log.debug("save snapshot as %s", filename)
                await page.screenshot(
                    {
                        'path': filename,
                        'fullPage': full_page,
                        'quality': quality,
                    }
                )
                await page.close()
            finally:
                urls.task_done()
    await browser.close()
    log.info("worker finished")


def viewport_size_cb(
    ctx: click.Context, param: click.Option, value: str
) -> ViewportSize:
    try:
        width, height = map(int, value.split('x'))
        return ViewportSize(width, height)
    except ValueError:
        raise click.BadParameter("viewport_size: WIDTHxHEIGHT")


def headers_cb(
    ctx: click.Context, param: click.Option, value: List[str]
) -> Dict[str, str]:
    try:
        return dict(v.split(':', 1) for v in value)
    except ValueError:
        raise click.BadParameter("bad header")


@click.command(help="take snapshot of webpage")
@click.option(
    '-i', '--input', help="input filename", type=click.File('r+'), default='-'
)
@click.option(
    '-o',
    '--output',
    help="snapshot output directory",
    type=click.Path(),
    default='./websnapshots',
)
@click.option('-w', '--workers', help="number of workers", type=int, default=10)
@click.option(
    '-V',
    '--viewport_size',
    help="viewport size",
    type=str,
    callback=viewport_size_cb,
    default='1366x768',
)
@click.option(
    '-H',
    '--header',
    'headers',
    help="extra header",
    type=str,
    callback=headers_cb,
    multiple=True,
)
@click.option('-f', '--full_page', help="full page snapshot", is_flag=True)
@click.option(
    '-q', '--quality', help="snapshot quality (1-100)", type=int, default=85,
)
@click.option(
    '-e', '--extension', '--ext', help="snapshot extension", default='.png'
)
@click.option(
    '-d',
    '--delay',
    help="delay after page load in seconds",
    type=float,
    default=5.0,
)
@click.option(
    '-t',
    '--timeout',
    help="maximum navigation timeout in seconds",
    type=float,
    default=15.0,
)
@click.option(
    '-l',
    '--log_level',
    help="logging level",
    type=str,
    callback=lambda ctx, param, value: value.upper(),
    default='warning',
)
def websnapshot(
    input: TextIO,
    output: str,
    workers: int,
    viewport_size: ViewportSize,
    headers: Dict[str, str],
    full_page: bool,
    quality: int,
    extension: str,
    delay: float,
    timeout: float,
    log_level: str,
) -> None:
    logging.basicConfig()
    log.setLevel(level=log_level)
    log.info("viewport size: %s", viewport_size)
    log.info("full page: %s", full_page)
    urls = asyncio.Queue()
    for url in input.read().splitlines():
        urls.put_nowait(url)
    output_dirname = pathlib.Path(output).expanduser().resolve()
    output_dirname.mkdir(parents=True, exist_ok=True)
    workers_num = min(urls.qsize(), workers)
    sem = asyncio.Semaphore(workers_num)
    tasks = [
        asyncio.ensure_future(
            worker(
                sem=sem,
                urls=urls,
                output_dirname=output_dirname,
                viewport_size=viewport_size,
                headers=headers,
                full_page=full_page,
                quality=quality,
                extension=extension,
                delay=delay,
                timeout=timeout,
            )
        )
        for _ in range(workers_num)
    ]
    _ = asyncio.get_event_loop().run_until_complete(
        asyncio.gather(*tasks, return_exceptions=True)
    )
    log.info("finished")

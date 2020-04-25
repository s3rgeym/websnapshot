import asyncio
import logging
import pathlib
import re
import sys
from functools import partial
from typing import TextIO, Tuple
from urllib.parse import unquote

import click
from pyppeteer import launch

__version__ = '0.1.6'

# Символы запрещенные в именах файлов в Linux, Mac и Windows
UNSAFE_CHARACTERS = re.compile(r'[\\/:*?"<>|]+')

log = logging.getLogger(__name__)
click.option = partial(click.option, show_default=True)


def filename_from_url(url: str, extension: str) -> str:
    return UNSAFE_CHARACTERS.sub('_', unquote(url)) + extension


async def worker(
    *,
    sem: asyncio.Semaphore,
    urls: asyncio.Queue,
    output_dirname: pathlib.Path,
    viewport: Tuple[int, int],
    full_page: bool,
    quality: int,
    extension: str,
    timeout: float,
) -> None:
    log.info("worker started")
    browser = await launch()
    while not urls.empty():
        async with sem:
            try:
                url = await urls.get()
                page = await browser.newPage()
                viewport_ = dict(zip(('width', 'height'), viewport))
                await page.setViewport(viewport_)
                await page.goto(url)
                await asyncio.sleep(timeout)
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


def validate_viewport(ctx, param, value) -> Tuple[int, int]:
    try:
        width, height = map(int, value.split('x'))
        return (width, height)
    except ValueError:
        raise click.BadParameter("viewport: WIDTHxHEIGHT")


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
@click.option(
    '-n', '--worker_num', help="number of workers", type=int, default=10
)
@click.option(
    '-s',
    '--viewport',
    help="viewport size",
    type=str,
    callback=validate_viewport,
    default='1366x768',
)
@click.option('-f', '--full_page', help="full page snapshot", is_flag=True)
@click.option(
    '-q', '--quality', help="snapshot quality (1-100)", type=int, default=85
)
@click.option(
    '-e', '--extension', '--ext', help="snapshot extension", default='.png'
)
@click.option(
    '-t', '--timeout', help="page load timeout", type=float, default=3.0
)
@click.option(
    '-l',
    '--log_level',
    help="logging level",
    type=str,
    callback=lambda ctx, param, value: value.upper(),
    default='info',
)
def websnapshot(
    input: TextIO,
    output: str,
    worker_num: int,
    viewport: Tuple[int, int],
    full_page: bool,
    quality: int,
    extension: str,
    timeout: float,
    log_level: str,
) -> None:
    logging.basicConfig()
    log.setLevel(level=log_level)
    log.info("viewport size: %s", viewport)
    log.info("full page: %s", full_page)
    urls = asyncio.Queue()
    for url in input.read().splitlines():
        urls.put_nowait(url)
    output_dirname = pathlib.Path(output).expanduser().resolve()
    output_dirname.mkdir(parents=True, exist_ok=True)
    n = min(urls.qsize(), worker_num)
    sem = asyncio.Semaphore(n)
    tasks = [
        asyncio.ensure_future(
            worker(
                sem=sem,
                urls=urls,
                output_dirname=output_dirname,
                viewport=viewport,
                full_page=full_page,
                quality=quality,
                extension=extension,
                timeout=timeout,
            )
        )
        for _ in range(n)
    ]
    _ = asyncio.get_event_loop().run_until_complete(
        asyncio.gather(*tasks, return_exceptions=True)
    )
    log.info("finished")

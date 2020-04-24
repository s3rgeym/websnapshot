import asyncio
import logging
import pathlib
import sys
from typing import TextIO, Tuple

import click
from pyppeteer import launch

__version__ = '0.1.3'


log = logging.getLogger(__name__)


def filename_from_url(url: str) -> str:
    return (
        url.replace('://', '_').replace('/', '_').replace('.', '_').rstrip('_')
    )


async def worker(
    *,
    sem: asyncio.Semaphore,
    urls: asyncio.Queue,
    output_dirname: pathlib.Path,
    viewport_size: Tuple[int, int],
    full_page: bool,
    pageload_timeout: float,
) -> None:
    log.info("worker started")
    browser = await launch()
    while not urls.empty():
        async with sem:
            try:
                url = await urls.get()
                page = await browser.newPage()
                viewport = dict(zip(('width', 'height'), viewport_size))
                await page.setViewport(viewport)
                await page.goto(url)
                await asyncio.sleep(pageload_timeout)
                filename = output_dirname.joinpath(
                    filename_from_url(url) + '.png'
                )
                log.debug("save snapshot %s", filename)
                await page.screenshot({'path': filename, 'fullPage': full_page})
                await page.close()
            finally:
                urls.task_done()
    await browser.close()
    log.info("worker finished")


def validate_viewport_size(ctx, param, value) -> Tuple[int, int]:
    try:
        width, height = map(int, value.split('x'))
        return (width, height)
    except ValueError:
        raise click.BadParameter("viewport_size: WIDTHxHEIGHT")


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
    '--viewport_size',
    help="viewport size",
    callback=validate_viewport_size,
    default='1366x768',
)
@click.option(
    '-f', '--full_page', help="full page snapshot", type=bool, default=False,
)
@click.option(
    '-t', '--pageload_timeout', help="page load timeout", type=float, default=3
)
@click.option(
    '-d', '--debug', help="enable debug mode", type=bool, default=False
)
def websnapshot(
    input: TextIO,
    output: str,
    worker_num: int,
    viewport_size: Tuple[int, int],
    full_page: bool,
    pageload_timeout: float,
    debug: bool,
) -> None:
    logging.basicConfig()
    if debug:
        log.setLevel(level=logging.DEBUG)
    log.debug('viewport size: %s', viewport_size)
    urls = asyncio.Queue()
    for url in input.read().splitlines():
        urls.put_nowait(url)
    output_dirname = pathlib.Path(__file__).parent.joinpath(output).resolve()
    output_dirname.mkdir(parents=True, exist_ok=True)
    N = min(urls.qsize(), worker_num)
    sem = asyncio.Semaphore(N)
    tasks = [
        asyncio.ensure_future(
            worker(
                sem=sem,
                urls=urls,
                output_dirname=output_dirname,
                viewport_size=viewport_size,
                full_page=full_page,
                pageload_timeout=pageload_timeout,
            )
        )
        for _ in range(N)
    ]
    _ = asyncio.get_event_loop().run_until_complete(
        asyncio.gather(*tasks, return_exceptions=True)
    )
    log.info("finished")

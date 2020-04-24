import asyncio
import logging
import os
import pathlib
import sys

import click
from pyppeteer import launch

__version__ = '0.1.2'


log = logging.getLogger(__name__)


def filename_from_url(url):
    return url.replace('://', '_').replace('/', '_').replace('.', '_').rstrip('_')


async def worker(urls, output_dirname, width, height, sem):
    log.info("worker started")
    browser = await launch()
    while not urls.empty():
        async with sem:
            try:
                url = await urls.get()
                page = await browser.newPage()
                await page.setViewport({ 'width': width, 'height': height })
                await page.goto(url)
                await asyncio.sleep(3)
                filename = output_dirname.joinpath(filename_from_url(url) + '.png')
                log.debug("save snapshot %s", filename)
                await page.screenshot({ 'path': filename })
                await page.close()
            finally:
                urls.task_done()
    log.info("worker finished")
    await browser.close()


@click.command(help="take snapshot of webpage")
@click.option('-i', '--input', help="input filename", type=click.File('r+'), default='-')
@click.option('-o', '--output', help="snapshot output directory", type=click.Path(), default='./websnapshots')
@click.option('-s', '--window_size', help="window size", default='1366x768')
@click.option('-n', '--worker_num', help="number of workers", type=int, default=os.cpu_count() - 1)
@click.option('-d', '--debug', help="enable debug mode", type=bool, default=False)
def websnapshot(input, output, window_size, worker_num, debug):
    logging.basicConfig()
    if debug:
        log.setLevel(level=logging.DEBUG)
    urls = asyncio.Queue()
    output_dirname = pathlib.Path(__file__).parent.joinpath(output).resolve()
    try:
        output_dirname.mkdir(parents=True, exist_ok=True)
    except:
        pass
    for url in input.read().splitlines():
        urls.put_nowait(url)
    width, height = map(int, window_size.split('x'))
    n = min(urls.qsize(), worker_num)
    sem = asyncio.Semaphore(n)
    tasks = [
        asyncio.ensure_future(
            worker(urls, output_dirname, width, height, sem)
        )
        for _ in range(n)
    ]
    _ = asyncio.get_event_loop().run_until_complete(
        asyncio.gather(*tasks, return_exceptions=True)
    )
    log.info("finished")

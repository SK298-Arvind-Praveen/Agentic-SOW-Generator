"""Dated INR presentation; native AWS USD evidence is never overwritten."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from html import unescape
import re
from urllib.request import Request, urlopen


FED_URL = 'https://www.federalreserve.gov/releases/h10/current/'
# Verified against the Federal Reserve H.10 release on 2026-11-19.
VERIFIED_FX = {'rate': '94.2400', 'date': '2026-11-13',
               'source': 'https://www.federalreserve.gov/releases/h10/hist/dat00_in.htm'}


def parse_federal_reserve_rate(html):
    clean = lambda value: re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', value))).strip()
    release = re.search(r'Release Date:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})', clean(html))
    if not release:
        raise ValueError('Missing Federal Reserve release date')
    published = datetime.strptime(release[1], '%B %d, %Y').date()
    rows = [[clean(cell) for cell in re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>', row, re.S | re.I)]
            for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.S | re.I)]
    dates = next(row[2:] for row in rows if row[:2] == ['COUNTRY', 'CURRENCY'])
    values = next(row[2:] for row in rows if row[:2] == ['INDIA', 'RUPEE'])
    for label, value in reversed(list(zip(dates, values))):
        if not re.fullmatch(r'\d+(?:\.\d+)?', value):
            continue
        observed = datetime.strptime(f'{label.replace(".", "")} {published.year}', '%b %d %Y').date()
        if observed > published:
            observed = observed.replace(year=published.year - 1)
        return {'rate': value, 'date': observed.isoformat(),
                'source': 'https://www.federalreserve.gov/releases/h10/hist/dat00_in.htm'}
    raise ValueError('No USD/INR observation in Federal Reserve release')


def pricing_presentation(result, config):
    """Convert the supported estimate, preserving partial status and exclusions."""
    if getattr(config, 'AWS_PRICING_DISPLAY_CURRENCY', 'USD').upper() != 'INR':
        return None
    native = result.get('monthly_cost')
    if native is None and result.get('status') == 'partial_priced':
        native = result.get('calculator_monthly_cost')
    if (native is None and result.get('status') in {'fallback_priced', 'hybrid_priced'}
            and not result.get('official_rate_components')):
        native = (result.get('fallback_estimate') or {}).get('monthly_base')
    if native is None or not Decimal(str(native)).is_finite() or Decimal(str(native)) <= 0:
        return None
    if result.get('currency', 'USD') != 'USD':
        raise ValueError('INR conversion requires native USD evidence')
    fx = {'rate': str(getattr(config, 'AWS_PRICING_USD_INR_RATE', VERIFIED_FX['rate'])),
          'date': getattr(config, 'AWS_PRICING_FX_DATE', VERIFIED_FX['date']),
          'source': getattr(config, 'AWS_PRICING_FX_SOURCE', VERIFIED_FX['source'])}
    if getattr(config, 'AWS_PRICING_FX_REFRESH', True):
        try:
            request = Request(FED_URL, headers={'User-Agent': 'SOWPricing/1.0'})
            with urlopen(request, timeout=8) as response:
                fx = parse_federal_reserve_rate(response.read().decode('utf-8'))
        except Exception as exc:
            # Never invent a replacement rate. Expose the dated snapshot and
            # retain refresh diagnostics in the audit without client error prose.
            fx['refresh_warning'] = str(exc)
    rate = Decimal(fx['rate'])
    if not rate.is_finite() or rate <= 0 or date.fromisoformat(fx['date']) > date.today():
        raise ValueError('Invalid dated USD/INR rate')
    if not str(fx['source']).startswith('https://'):
        raise ValueError('USD/INR rate requires an auditable HTTPS source')
    converted = (Decimal(str(native)) * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {'currency': 'INR', 'monthly_cost': str(converted), 'native_monthly_cost': str(native),
            'native_currency': 'USD', 'fx': fx}

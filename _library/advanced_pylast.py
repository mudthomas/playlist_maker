import pylast as pl


class advanced_pylast_User(pl.User):
    PERIOD_OVERALL = "overall"

    def get_top_artists(self, period=PERIOD_OVERALL, limit=None, page=1):
        """Returns the top artists played by a user.
        * period: The period of time. Possible values:
          o PERIOD_OVERALL
          o PERIOD_7DAYS
          o PERIOD_1MONTH
          o PERIOD_3MONTHS
          o PERIOD_6MONTHS
          o PERIOD_12MONTHS
        """
        params = self._get_params()
        params["period"] = period
        params["page"] = page
        if limit:
            params["limit"] = limit
        doc = self._request(self.ws_prefix + ".getTopArtists", True, params)
        return pl._extract_top_artists(doc, self.network)

def fetch_latest_issuances(self):
        current_year = datetime.now().year
        url = f"{self.base_url}/mc-{current_year}/"
        logger.info(f"Fetching SEC issuances from {url}...")
        
        candidates = []
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Check table rows first for SEC circular tables
            rows = soup.find_all("tr")
            if rows:
                for row in rows:
                    anchors = row.find_all("a", href=True)
                    if not anchors:
                        continue
                    
                    # Target the first <td> for the title, fallback to row text if no <td> exists
                    tds = row.find_all("td")
                    row_text = tds[0].get_text(strip=True) if tds else row.get_text(" ", strip=True)
                    
                    for anchor in anchors:
                        href = anchor["href"]
                        candidates.append({
                            "title": row_text or "SEC Issuance",
                            "url": href if href.startswith("http") else f"{self.base_url}{href}",
                            "regulator": "SEC"
                        })
            else:
                # General fallback for anchor lists
                for anchor in soup.find_all("a", href=True):
                    href = anchor["href"]
                    text = anchor.get_text(strip=True)
                    candidates.append({
                        "title": text or href,
                        "url": href if href.startswith("http") else f"{self.base_url}{href}",
                        "regulator": "SEC"
                    })

            logger.info(f"Successfully extracted {len(candidates)} candidates from SEC.")
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to fetch SEC issuances: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in SEC adapter: {e}")

        return candidates

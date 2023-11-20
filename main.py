import time
import os
from json import JSONDecodeError
import logging

from locust import HttpUser, task, between

# membership_no = "AHMY625111"
MEMBERSHIP_NO = "AHMY552226"

VITALITY_HOSTNAME = "https://qa.vitality.aia.com/vitality"
NALURI_HOSTNAME = "https://staging-ah.naluri.net"

TOKEN_BASE_URL = "/security/v1/tokens/generate?entity-id=9&app-id=9d62c962-db2e-4fcf-b856-5da15d21fb72&membership-no="

TOKEN_REQUEST_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": "Basic YzY2YWIyNDYtMzA2MS00ZDA4LWI2ODUtMWEwNTg2OGI0ZmE4OmI4NDBiZjI2LTkwMjUtNDdlMC04YWVjLThmYTkwOGI4MTEzZQ==",
}

VALIDATE_BASE_URL = "/core/v3/crm/member/validate/benefit?member-identifier-reference-type=MEMBERSHIPNO&partner-id=NALURISG&member-identifier-reference="
MEMBER_VALIDATE_REQUEST_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Vitality-Legal-Entity-Id": "9",
    "X-AIA-Request-Id": "CDM",
}

REGISTER_IMAGE_BASE_URL = (
    "/core/v2/challenges/food/register-image?number-of-images=1&membership-no="
)
ACCESS_TOKEN_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Vitality-Legal-Entity-Id": "9",
    "X-AIA-Request-Id": "CDM",
}

classification_base_url = "/core/v2/challenges/food/classification?membership-no="


def _get_image_part(file_path, file_content_type="image/jpeg"):
    file_name = os.path.basename(file_path)
    file_content = open(file_path, "rb")
    return file_name, file_content, file_content_type


class CDMUsers(HttpUser):
    """Class representing CDMUsers"""

    # Member validation API
    validate_url = f"{VALIDATE_BASE_URL}{MEMBERSHIP_NO}"
    # Register image API
    register_image_url = f"{REGISTER_IMAGE_BASE_URL}{MEMBERSHIP_NO}"
    # Classification API
    classification_url = f"{classification_base_url}{MEMBERSHIP_NO}&food-journal-id="

    def on_start(self):
        wait_time = between(1, 5)
        token_url = TOKEN_BASE_URL + MEMBERSHIP_NO
        logging.info(token_url)
        global token
        with self.client.post(
            token_url, headers=TOKEN_REQUEST_HEADERS, catch_response=True
        ) as response:
            try:
                response_json = response.json()
                jwt = response_json["jwt"]
                logging.info(jwt)
                token = jwt
            except JSONDecodeError:
                response.failure("Response could not be decoded as JSON")
            except KeyError:
                response.failure("Response did not contain expected key 'greeting'")

    # @task
    def validate_member_benefit(self):
        # logging.info(validate_url)
        with self.client.get(
            self.validate_url, headers=MEMBER_VALIDATE_REQUEST_HEADERS
        ) as response:
            logging.info(response.json())

    @task
    def food_journal(self):
        """Function to test food journal feature"""
        # Step 1: Get pre-signed URL from the first API
        logging.info(self.register_image_url)
        ACCESS_TOKEN_HEADERS["Authorization"] = "Bearer " + token
        pre_signed_url = None
        with self.client.get(
            self.register_image_url, headers=ACCESS_TOKEN_HEADERS, catch_response=True
        ) as upload_response:
            try:
                if upload_response.status_code != 200:
                    upload_response.failure(
                        f"Encountered error when requesting pre-signed url {upload_response.status_code}"
                    )
                else:
                    response_json = upload_response.json()
                    pre_signed_url = response_json["registerFoodImage"][0]["uploadUrl"]
            except JSONDecodeError:
                upload_response.failure("Response could not be decoded as JSON")
        logging.info(pre_signed_url)

        # Step 2: Load and upload the image to the second API
        # food_image = _get_image_part("images/img1.png")
        r_data = None
        with open("images/img1.png", "rb") as food_image:
            with self.client.put(
                pre_signed_url,
                data=food_image,
                headers={"Content-Type": "image/png"},
                catch_response=True,
            ) as upload_response:
                logging.info(upload_response.json())
                if upload_response.status_code != 200:
                    upload_response.failure(
                        f"encountered error when uploading image {upload_response.status_code}"
                    )
                else:
                    r_data = upload_response.json()

        # Step 3: Call the third API to retrieve classification data
        logging.info(f"upload image response {r_data}")
        logging.info(
            f"final classification url {self.classification_url}{r_data['id']}"
        )

        max_retries = 3
        for attempt in range(max_retries):
            with self.client.get(
                f"{self.classification_url}{r_data['id']}",
                headers=ACCESS_TOKEN_HEADERS,
                catch_response=True,
            ) as classification_response:
                logging.info(classification_response)

                try:
                    if classification_response.status_code != 200:
                        classification_response.failure(
                            f"encountered error when retrieving classification data {classification_response.status_code}"
                        )
                    else:
                        data = classification_response.json()
                        logging.info(data)
                        if data.get("id") is not None:
                            break  # Break if 'id' is non-null
                        elif attempt < max_retries - 1:
                            classification_response.failure(
                                f"no classification found for food-journal-id {r_data['id']}"
                            )
                            time.sleep(1)  # Wait for 1 second before the next retry
                        else:
                            logging.error(
                                f"Failed after 3 attempts for {r_data['id']}"
                            )
                            classification_response.failure(
                                f"no classification found for food-journal-id = {r_data['id']}"
                            )
                except JSONDecodeError:
                    classification_response.failure(
                        "Response could not be decoded as JSON"
                    )
                except Exception as e:
                    logging.error(e.__str__)
                    classification_response.failure(
                        f"Encounter exception {r_data['id']}"
                    )
